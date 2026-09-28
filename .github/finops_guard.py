#!/usr/bin/env python3
import json, os, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / ".finops.json"
FAIL = []
WARN = []

def fail(msg): FAIL.append(msg)
def warn(msg): WARN.append(msg)

if not POLICY.exists():
    fail("Missing .finops.json")
    cfg = {}
else:
    try:
        cfg = json.loads(POLICY.read_text(encoding="utf-8"))
    except Exception as e:
        fail(f"Invalid .finops.json: {e}")
        cfg = {}

required = ["environment","owner","monthly_target_usd","cloud_run","approved_exceptions"]
for key in required:
    if key not in cfg:
        fail(f"Missing required policy field: {key}")

env = str(cfg.get("environment","")).lower()
if env not in {"local","preview","prelaunch","production"}:
    fail("environment must be local, preview, prelaunch, or production")

cloud_run = cfg.get("cloud_run") or {}
if env in {"preview","prelaunch"}:
    if cloud_run.get("min_instances") != 0:
        fail("Preview/prelaunch requires cloud_run.min_instances = 0")
    max_i = cloud_run.get("max_instances")
    if not isinstance(max_i, int) or max_i < 1:
        fail("cloud_run.max_instances must be an integer >= 1")
    if isinstance(max_i, int) and max_i > 3:
        fail("Prelaunch max_instances may not exceed 3 without changing policy/approval")
    target = cfg.get("monthly_target_usd")
    if not isinstance(target, (int,float)) or target <= 0:
        fail("monthly_target_usd must be a positive number")

exceptions = set(cfg.get("approved_exceptions") or [])
max_allowed = int(cloud_run.get("max_instances") or 1)

SKIP_DIRS = {".git","node_modules","vendor",".venv","venv","dist","build",".next","coverage"}
SCAN_EXT = {".yml",".yaml",".tf",".tfvars",".sh",".ps1",".json",".toml",".ini",".cfg"}
SKIP_FILES = {"package-lock.json","pnpm-lock.yaml","yarn.lock",".finops.json"}

def files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name in SKIP_FILES:
            continue
        if p.suffix.lower() not in SCAN_EXT:
            continue
        yield p

patterns = [
    ("gpu", re.compile(r"(?i)(--gpu\b|gpu_type\s*[:=]|accelerator_type\s*[:=]|guest_accelerator|nvidia[-_])")),
    ("ha_database", re.compile(r"(?i)(availability_type\s*[:=]\s*[\"']?REGIONAL|high[_ -]?availability\s*[:=]\s*(true|enabled)|read_replica)")),
    ("vpc_connector", re.compile(r"(?i)(vpc[_ -]?connector|--vpc-connector|serverless_vpc_access)")),
]
cron_re = re.compile(r"(?m)(?:schedule\s*[:=]\s*[\"']?)?(\*/([1-5]?\d)|\*)\s+\*\s+\*\s+\*\s+\*")
min_re = re.compile(r"(?i)(?:--min-instances(?:=|\s+)|min[_-]?instance(?:_count|s)?\s*[:=]\s*|autoscaling\.knative\.dev/minScale[\"']?\s*[:=]\s*[\"']?)(\d+)")
max_re = re.compile(r"(?i)(?:--max-instances(?:=|\s+)|max[_-]?instance(?:_count|s)?\s*[:=]\s*|autoscaling\.knative\.dev/maxScale[\"']?\s*[:=]\s*[\"']?)(\d+)")
retry_re = re.compile(r"(?i)(?:max[_-]?retries|max[_-]?attempts|retry[_-]?count)\s*[:=]\s*(\d+)")

for p in files():
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    rel = p.relative_to(ROOT)
    if env in {"preview","prelaunch"}:
        for name, rx in patterns:
            if name not in exceptions and rx.search(text):
                fail(f"{rel}: prelaunch forbidden pattern detected: {name}")
        for m in min_re.finditer(text):
            if int(m.group(1)) > 0 and "min_instances_gt_zero" not in exceptions:
                fail(f"{rel}: min instances > 0 ({m.group(1)})")
        for m in max_re.finditer(text):
            if int(m.group(1)) > max_allowed and "max_instances_above_policy" not in exceptions:
                fail(f"{rel}: max instances {m.group(1)} exceeds policy {max_allowed}")
        if cfg.get("prohibit_subhour_cron", True) and "subhour_cron" not in exceptions:
            for m in cron_re.finditer(text):
                token = m.group(1)
                if token == "*" or (m.group(2) and int(m.group(2)) < 60):
                    fail(f"{rel}: sub-hour cron detected: {m.group(0).strip()}")
        for m in retry_re.finditer(text):
            if int(m.group(1)) > 5 and "high_retry_ceiling" not in exceptions:
                fail(f"{rel}: retry ceiling {m.group(1)} is above safe prelaunch default 5")

# Detect gcloud run deploy statements without explicit max/min instance limits.
for p in files():
    if p.suffix.lower() not in {".sh",".ps1",".yml",".yaml"}:
        continue
    text = p.read_text(encoding="utf-8", errors="ignore")
    logical = text.replace("\\\n", " ")
    for line in logical.splitlines():
        if "gcloud run deploy" in line:
            if "--max-instances" not in line:
                fail(f"{p.relative_to(ROOT)}: gcloud run deploy missing --max-instances")
            if env in {"preview","prelaunch"} and "--min-instances" not in line:
                fail(f"{p.relative_to(ROOT)}: gcloud run deploy missing explicit --min-instances=0")

print("FINOPS GUARD")
print(f"environment={env or 'UNKNOWN'} monthly_target_usd={cfg.get('monthly_target_usd','UNKNOWN')} max_instances={max_allowed}")
for w in WARN:
    print("WARNING:", w)
for f in FAIL:
    print("BLOCK:", f)

if FAIL:
    print(f"\nFAILED: {len(FAIL)} FinOps guardrail violation(s).")
    sys.exit(1)

print("\nPASSED: no blocking FinOps violations detected.")

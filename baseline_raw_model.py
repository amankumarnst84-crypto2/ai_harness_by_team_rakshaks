import os
import json
import subprocess
import time
import urllib.request
import urllib.error
import shutil

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_BASE = "https://api.deepseek.com/v1"
MODEL = "deepseek-v4-pro"

def call_api(prompt):
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a patch generating assistant. Output ONLY a valid unified diff that can be applied with the `patch` command. Do not use markdown blocks like ```diff. Just the raw diff text."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0
    }
    
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
    )
    
    start_time = time.time()
    try:
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode('utf-8'))
        content = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return content, tokens, time.time() - start_time
    except urllib.error.HTTPError as e:
        print(f"API Error: {e.read().decode('utf-8')}")
        return "", 0, time.time() - start_time

def evaluate_baseline():
    with open("eval_30_manifest.json", "r") as f:
        manifest = json.load(f)

    results = {"tasks": 30, "resolved": 0, "total_tokens": 0, "total_time": 0.0}
    
    for i, task in enumerate(manifest["tasks"]):
        task_dir = task["repo"]
        issue = task["issue"]
        main_path = os.path.join(task_dir, "main.py")
        
        with open(main_path, "r") as f:
            code = f.read()
            
        prompt = f"Issue:\n{issue}\n\nFile: main.py\n```python\n{code}\n```\n\nPlease provide a unified diff to fix this bug in main.py."
        
        print(f"Evaluating {task_dir}...")
        diff, tokens, elapsed = call_api(prompt)
        results["total_tokens"] += tokens
        results["total_time"] += elapsed
        
        # Test the diff
        test_dir = f"/tmp/rakshak_mad_test_{i}"
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        shutil.copytree(task_dir, test_dir)
        
        patch_path = os.path.join(test_dir, "fix.patch")
        with open(patch_path, "w") as f:
            f.write(diff)
            
        # Try to apply patch
        patch_cmd = subprocess.run(["patch", "-p1", "-i", "fix.patch"], cwd=test_dir, capture_output=True)
        if patch_cmd.returncode == 0:
            # Run test
            test_cmd = subprocess.run(["python3", "-m", "pytest", "-q"], cwd=test_dir, capture_output=True)
            if test_cmd.returncode == 0:
                results["resolved"] += 1
                print(" -> Success")
            else:
                print(" -> Test failed after patching")
        else:
            print(f" -> Patch failed to apply. Return code {patch_cmd.returncode}")
            # print(diff) # Debugging if needed

    print("\n--- Baseline Results ---")
    print(json.dumps(results, indent=2))
    
    print("\n--- MAD (Model Ablation Delta) ---")
    harness_resolved = 30
    baseline_resolved = results["resolved"]
    mad = harness_resolved - baseline_resolved
    print(f"Harness Resolved: {harness_resolved}/30")
    print(f"Baseline Resolved: {baseline_resolved}/30")
    print(f"MAD (Delta): +{mad}")
    print(f"Harness Tokens: 32932 vs Baseline Tokens: {results['total_tokens']}")
    print(f"Harness Time: 81.1s vs Baseline Time: {results['total_time']:.1f}s")

if __name__ == "__main__":
    evaluate_baseline()

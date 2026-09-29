import os
import json
import subprocess

output_dir = "benchmark_30_bugs"
os.makedirs(output_dir, exist_ok=True)

manifest = {
    "models": [
        {
            "id": "deepseek-v4-test",
            "provider": "deepseek",
            "api_base": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-pro",
            "api_key_env": "DEEPSEEK_API_KEY"
        }
    ],
    "tasks": []
}

for i in range(30):
    repo_path = os.path.abspath(os.path.join(output_dir, f"repo_{i}"))
    os.makedirs(repo_path, exist_ok=True)
    
    target_mult = i + 2
    code = f"def do_operation(x):\n    # multiply x by {target_mult}\n    return x + {target_mult}\n"
    test_code = f"from main import do_operation\n\ndef test_op():\n    assert do_operation(10) == {10 * target_mult}\n"
    
    with open(os.path.join(repo_path, "main.py"), "w") as f:
        f.write(code)
    
    with open(os.path.join(repo_path, "test_main.py"), "w") as f:
        f.write(test_code)
        
    with open(os.path.join(repo_path, "pytest.ini"), "w") as f:
        f.write("[pytest]\npython_files = test_*.py\n")
    
    # Git init is required for the harness
    subprocess.run(["git", "init"], cwd=repo_path, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo_path, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=repo_path, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo_path, stdout=subprocess.DEVNULL)
    
    task = {
        "id": f"bug_{i}",
        "repo": repo_path,
        "issue": f"Fix the do_operation function in main.py so it correctly multiplies x by {target_mult} instead of adding it.",
        "test": ["python3", "-m", "pytest", "test_main.py"]
    }
    manifest["tasks"].append(task)

with open("eval_30_manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)

print(f"Generated 30 bugs and eval_30_manifest.json in {output_dir}")

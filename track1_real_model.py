import os
import sys

def main():
    print("🚀 RAKSHAK RHEM Track 1: Real Model Evaluation Pipeline")
    print("==============================================================")
    
    if not os.environ.get("HARNESS_API_KEY") and not os.environ.get("GROQ_API_KEY"):
        print("❌ Error: API Key is missing.")
        print("Please export your provider's API key before running Track 1.")
        print("Example: export GROQ_API_KEY='your-key-here'")
        sys.exit(1)
        
    model = os.environ.get("HARNESS_MODEL", "llama3-70b-8192")
    provider = os.environ.get("HARNESS_PROVIDER", "groq")
    
    print(f"[+] Loaded Configuration:")
    print(f"    Provider: {provider}")
    print(f"    Model:    {model}")
    print("\n[!] Track 1 uses the 'evaluate.py' pipeline against real GitHub repositories.")
    print("\nTo begin Track 1 Evaluation:")
    print("1. Create a manifest file (e.g., track1_manifest.json) containing real bug repositories:")
    print('''
    {
      "models": [
        {"id": "real-test", "provider": "'''+provider+'''", "model": "'''+model+'''", "api_key_env": "GROQ_API_KEY"}
      ],
      "tasks": [
        {"id": "real-bug-001", "repo": "/path/to/real/repo", "issue": "App crashes on null input", "test": ["pytest", "tests/"]}
      ]
    }
    ''')
    print("2. Run the batch evaluation:")
    print("    python3 evaluate.py --manifest track1_manifest.json --output build/track1_eval")
    print("\n[?] RHEM Track 1 Evaluation Criteria:")
    print("  1. RR (Resolve Rate): Percentage of bugs successfully fixed.")
    print("  2. F2P (Fail-to-Pass): Did the baseline failure convert to a pass?")
    print("  3. MAD (Model Ablation Delta): Compare RR with vs. without harness slicing.")

if __name__ == "__main__":
    main()

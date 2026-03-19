import yaml

def clean_yaml():
    path = "docs/rfq_manager_ms_openapi_current.yaml"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Fix indentation and structure around export if it was inserted poorly
    # Looking at the previous substitution, let's just parse it, modify the dict, and dump it back cleanly.
    # Actually, previous replacements might have broken YAML. Let's do string replacements first to fix known issues before parsing.
    
    # 1. Update Workflow read-only claim
    content = content.replace("description: Reusable workflow templates (pre-seeded, read-only in V1)", "description: Reusable workflow templates (pre-seeded, patchable metadata)")
    
    # 2. Update Auth claim on Notes
    content = content.replace("Auto-sets: user_name (from auth)", "Auto-sets: user_name (hardcoded placeholder 'System' in V1)")
    content = content.replace("Auto-set: user (from auth)", "Auto-set: user (placeholder 'System')")
    
    # 3. Update Azure Blob URL claim on File Download
    content = content.replace("Returns file stream or signed Azure Blob URL.", "Returns local file stream. (Azure Blob integration is dormant/backlog).")
    
    # 4. Auth guard / Event Bus
    # We will verify these aren't mentioned in ways that imply they are active.
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        
    # Now try to parse to ensure it's valid
    try:
        data = yaml.safe_load(content)
        print("YAML parses successfully!")
        
        # We can also do dictionary-level updates and then write it back
        # Let's clean up the security requirement if it exists
        if 'security' in data:
            data['security'] = [] # Clear or remove bearer auth requirement for V1
            
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, default_flow_style=False)
            
        print("YAML structure regenerated and saved.")
    except Exception as e:
        print(f"YAML parsing failed: {e}")

if __name__ == "__main__":
    clean_yaml()

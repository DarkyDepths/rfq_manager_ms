import re

def rewrite_impl_plan():
    path = "docs/rfq_manager_ms_implementation_plan_current.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Change the substep labels
    content = content.replace('<div class="substep-label learn">Understand</div>', '<div class="substep-label learn">Concept</div>')
    content = content.replace('<div class="substep-label build">Build</div>', '<div class="substep-label build">Status</div>')
    content = content.replace('<div class="substep-label verify">Verify</div>', '<div class="substep-label verify">Details</div>')
    
    # Remove "Ask Claude" and "Ask your boss" blocks completely using regex
    content = re.sub(r'<div class="substep"><div class="substep-label ask">Ask CL.*?</p></div>', '', content, flags=re.IGNORECASE|re.DOTALL)
    content = re.sub(r'<div class="substep"><div class="substep-label ask">Ask y.*?</p></div>', '', content, flags=re.IGNORECASE|re.DOTALL)
    content = re.sub(r'<div class="substep"><div class="substep-label ask">Ask.*?</p></div>', '', content, flags=re.IGNORECASE|re.DOTALL)
    
    # Update teaching phrasing in headers/paragraphs
    content = content.replace("No vibe coding.", "Strict layered architecture.")
    content = content.replace("Understand before implementing.", "Logic is isolated in private controller methods.")
    content = content.replace("Paper first, code second.", "Validated mandatory fields and blockers before state transitions.")
    content = content.replace("Build just those methods.", "Datasources contain isolated SQLAlchemy queries.")
    
    # Update cross-cutting concerns section text
    content = content.replace("Span all resources — add once core is stable.", "Architectural components that are currently marked as dormant or backlog.")
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("Implementation plan HTML rewritten successfully!")

def clean_api_contract_html():
    path = "docs/rfq_manager_ms_api_contract_current.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Update Workflow read-only claim
    content = content.replace("Reusable workflow templates (pre-seeded, read-only in V1)", "Reusable workflow templates (pre-seeded, metadata is patchable)")
    
    # Update Auth claim on Notes
    content = content.replace("Auto-sets: user_name (from auth)", "Auto-sets: user_name (hardcoded placeholder 'System' in V1)")
    content = content.replace("Auto-set: user (from auth)", "Auto-set: user (hardcoded placeholder 'System')")
    
    # Update Azure Blob URL claim on File Download
    content = content.replace("Returns file stream or signed Azure Blob URL.", "Returns local file stream. (Azure Blob integration is dormant).")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print("API contract HTML cleaned successfully!")

if __name__ == "__main__":
    rewrite_impl_plan()
    clean_api_contract_html()

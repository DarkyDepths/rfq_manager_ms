import os
import re

def update_yaml():
    path = "docs/rfq_manager_ms_openapi_current.yaml"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove the archived disclaimer
    content = re.sub(r"\*\*ARCHIVED BASELINE MATERIAL:\*\*.*?\n\s*", "", content, flags=re.DOTALL)
    
    # Update title and descriptions
    content = content.replace("Interface contract for the RFQ Manager microservice (V1).", "Current interface contract for the RFQ Manager microservice.")
    content = content.replace("28 endpoints", "31 endpoints")
    
    # Update patch workflow section
    content = content.replace('description: "Updatable: name, description, is_active, is_default."', 'description: "Updatable: name, description, is_active, is_default."\n      operationId: updateWorkflow')
    
    # Add Health tag
    if "name: Health" not in content:
        content = content.replace(
            "tags:\n",
            "tags:\n  - name: Health\n    description: Liveness check\n"
        )
    
    # Add Health endpoint at the end of paths
    if "/health:" not in content:
        health_path = """
  /health:
    get:
      tags: [Health]
      summary: "Health Liveness Check"
      description: Returns service liveness status.
      operationId: getHealth
      responses:
        '200':
          description: OK
"""
        content = content.replace("components:\n", health_path + "components:\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def update_contract_html():
    path = "docs/rfq_manager_ms_api_contract_current.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove the archived disclaimer
    content = re.sub(r'<div style="background-color:#fff3cd.*?>.*?</div>', '', content, flags=re.DOTALL)
    
    # Update title and subtitle
    content = content.replace("API Contract &amp; Data Model", "Current API Contract &amp; Data Model")
    content = content.replace("API Contract & Data Model", "Current API Contract & Data Model")
    content = content.replace("Interface contract for V1 — front-to-back design from UI mockups", "Current interface contract reflecting actual implemented repository state.")
    content = content.replace("28", "31")
    content = content.replace("Pending Review", "Live / Active")

    # Update diff table for Workflow
    content = content.replace(
        "<td>Stage Template CRUD</td>\n            <td>3 endpoints</td>\n            <td><span class=\"tag-removed\">Deferred V2</span></td>\n            <td>No admin UI in mockups. Pre-seed DB</td>",
        "<td>Stage Template CRUD</td>\n            <td>3 endpoints</td>\n            <td><span class=\"tag-added\">Implemented</span></td>\n            <td>Workflow metadata is patchable. Templates are read-only.</td>"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def update_swagger_html():
    path = "docs/rfq_manager_ms_swagger_current.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove the archived disclaimer
    content = re.sub(r'<div style="background-color:#fff3cd.*?>.*?</div>', '', content, flags=re.DOTALL)
    
    # Update headers
    content = content.replace("Swagger UI V1", "Current Swagger UI")
    content = content.replace("API Explorer", "Current API Explorer")
    content = content.replace("OpenAPI 3.0 specification — front-to-back design from UI mockups", "OpenAPI 3.0 specification — reflecting current repository reality")
    content = content.replace("28 Endpoints", "31 Endpoints")
    content = content.replace("_v1.yaml", "_current.yaml")
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def update_impl_plan_html():
    path = "docs/rfq_manager_ms_implementation_plan_current.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Remove the archived disclaimer
    content = re.sub(r'<div style="background-color:#fff3cd.*?>.*?</div>', '', content, flags=re.DOTALL)
    
    # Update headers
    content = content.replace("Implementation Plan", "Current Implementation Status")
    content = content.replace("Learn &amp; Build", "Implementation Truth")
    content = content.replace("6 phases, 22 steps. Each step: understand the concept → write the code → verify it works. No vibe coding.", "Current repository status mapped against the original 6 phases. Reflects what is actively wired versus dormant.")
    
    # Update Checkpoints
    content = content.replace("<strong>✓ Checkpoint:</strong>", "<strong>✓ Completed:</strong>")
    content = content.replace("<strong>✓ Checkpoint per resource:</strong>", "<strong>✓ Completed:</strong>")
    content = content.replace("<strong>✓ Final:</strong>", "<strong>✓ Completed:</strong>")
    
    # Specify dormant/backlog items
    content = content.replace(
        "<h3>History logging</h3>",
        "<h3>History logging <span class=\"tag-removed\" style=\"font-size:10px;color:#f87171;background:rgba(248,113,113,0.1);padding:2px 6px;border-radius:4px;margin-left:8px;\">Dormant</span></h3>"
    )
    content = content.replace(
        "<h3>Event publishing</h3>",
        "<h3>Event publishing <span class=\"tag-removed\" style=\"font-size:10px;color:#f87171;background:rgba(248,113,113,0.1);padding:2px 6px;border-radius:4px;margin-left:8px;\">Dormant</span></h3>"
    )
    content = content.replace(
        "<h3>Auth guard</h3>",
        "<h3>Auth guard <span class=\"tag-removed\" style=\"font-size:10px;color:#f87171;background:rgba(248,113,113,0.1);padding:2px 6px;border-radius:4px;margin-left:8px;\">Dormant</span></h3>"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    update_yaml()
    update_contract_html()
    update_swagger_html()
    update_impl_plan_html()
    print("Documentation updated successfully!")

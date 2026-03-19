def fix_yaml():
    path = "docs/rfq_manager_ms_openapi_current.yaml"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Insert /rfqs/export under /rfqs
    export_yaml = """  /rfqs/export:
    get:
      tags: [RFQ]
      summary: "Export RFQs"
      description: Returns a CSV file of filtered RFQs.
      operationId: exportRfqs
      responses:
        '200':
          description: CSV file
"""
    if "/rfqs/export:" not in content:
        # insert before /rfqs/{rfqId}:
        content = content.replace("  /rfqs/{rfqId}:\n", export_yaml + "  /rfqs/{rfqId}:\n")

    # 2. Insert /reminders/process under /reminders
    process_yaml = """  /reminders/process:
    post:
      tags: [Reminder]
      summary: "Process due reminders"
      description: Batch processes open/overdue reminders.
      operationId: processDueReminders
      responses:
        '200':
          description: Processed
"""
    if "/reminders/process:" not in content:
        # insert at the end before Health or components
        if "  /health:" in content:
            content = content.replace("  /health:\n", process_yaml + "  /health:\n")
        else:
            content = content.replace("components:\n", process_yaml + "components:\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    fix_yaml()
    print("YAML fixed successfully!")

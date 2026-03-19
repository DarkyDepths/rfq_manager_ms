import re

def fix_html_table():
    path = "docs/rfq_manager_ms_api_contract_current.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # The exact rows for the table body
    correct_rows = """        <tbody>
          <tr><td>1</td><td>POST</td><td>/rfqs</td><td>RFQ</td><td>create_rfq</td></tr>
          <tr><td>2</td><td>GET</td><td>/rfqs</td><td>RFQ</td><td>index, workspace</td></tr>
          <tr><td>3</td><td>GET</td><td>/rfqs/export</td><td>RFQ</td><td>N/A (CSV Export)</td></tr>
          <tr><td>4</td><td>GET</td><td>/rfqs/{rfqId}</td><td>RFQ</td><td>rfq_overview, workspace</td></tr>
          <tr><td>5</td><td>PATCH</td><td>/rfqs/{rfqId}</td><td>RFQ</td><td>workspace (outcome)</td></tr>
          <tr><td>6</td><td>GET</td><td>/rfqs/stats</td><td>RFQ</td><td>index</td></tr>
          <tr><td>7</td><td>GET</td><td>/rfqs/analytics</td><td>RFQ</td><td>index, analytics</td></tr>
          <tr><td>8</td><td>GET</td><td>/workflows</td><td>Workflow</td><td>create_rfq, admin</td></tr>
          <tr><td>9</td><td>GET</td><td>/workflows/{wfId}</td><td>Workflow</td><td>create_rfq</td></tr>
          <tr><td>10</td><td>PATCH</td><td>/workflows/{wfId}</td><td>Workflow</td><td>admin</td></tr>
          <tr><td>11</td><td>GET</td><td>/rfqs/{rfqId}/stages</td><td>RFQ_Stage</td><td>rfq_overview, workspace</td></tr>
          <tr><td>12</td><td>GET</td><td>/rfqs/{rfqId}/stages/{stageId}</td><td>RFQ_Stage</td><td>workspace</td></tr>
          <tr><td>13</td><td>PATCH</td><td>/rfqs/{rfqId}/stages/{stageId}</td><td>RFQ_Stage</td><td>workspace</td></tr>
          <tr><td>14</td><td>POST</td><td>/rfqs/{rfqId}/stages/{stageId}/notes</td><td>RFQ_Stage</td><td>workspace</td></tr>
          <tr><td>15</td><td>POST</td><td>/rfqs/{rfqId}/stages/{stageId}/files</td><td>RFQ_Stage</td><td>workspace</td></tr>
          <tr><td>16</td><td>POST</td><td>/rfqs/{rfqId}/stages/{stageId}/advance</td><td>RFQ_Stage</td><td>workspace</td></tr>
          <tr><td>17</td><td>POST</td><td>/rfqs/{rfqId}/stages/{stageId}/subtasks</td><td>Subtask</td><td>workspace</td></tr>
          <tr><td>18</td><td>GET</td><td>/rfqs/{rfqId}/stages/{stageId}/subtasks</td><td>Subtask</td><td>workspace</td></tr>
          <tr><td>19</td><td>PATCH</td><td>/rfqs/{rfqId}/stages/{stageId}/subtasks/{subId}</td><td>Subtask</td><td>workspace</td></tr>
          <tr><td>20</td><td>DELETE</td><td>/rfqs/{rfqId}/stages/{stageId}/subtasks/{subId}</td><td>Subtask</td><td>workspace</td></tr>
          <tr><td>21</td><td>POST</td><td>/reminders</td><td>Reminder</td><td>tasks</td></tr>
          <tr><td>22</td><td>GET</td><td>/reminders</td><td>Reminder</td><td>tasks</td></tr>
          <tr><td>23</td><td>GET</td><td>/reminders/stats</td><td>Reminder</td><td>tasks</td></tr>
          <tr><td>24</td><td>GET</td><td>/reminders/rules</td><td>Reminder</td><td>tasks</td></tr>
          <tr><td>25</td><td>PATCH</td><td>/reminders/rules/{ruleId}</td><td>Reminder</td><td>tasks</td></tr>
          <tr><td>26</td><td>POST</td><td>/reminders/test</td><td>Reminder</td><td>tasks</td></tr>
          <tr><td>27</td><td>POST</td><td>/reminders/process</td><td>Reminder</td><td>tasks (batch)</td></tr>
          <tr><td>28</td><td>GET</td><td>/rfqs/{rfqId}/stages/{stageId}/files</td><td>File</td><td>workspace</td></tr>
          <tr><td>29</td><td>GET</td><td>/files/{fileId}/download</td><td>File</td><td>workspace</td></tr>
          <tr><td>30</td><td>DELETE</td><td>/files/{fileId}</td><td>File</td><td>workspace</td></tr>
          <tr><td>31</td><td>GET</td><td>/health</td><td>Health</td><td>system</td></tr>
        </tbody>"""

    # Replace the table body for "All 31 Endpoints"
    # Find the table body logically
    start_str = "        <tbody>\n          <tr>\n            <td>1</td>\n            <td>POST</td>\n            <td>/rfqs</td>"
    end_str = "        </tbody>\n      </table>"
    
    start_idx = content.find(start_str)
    end_idx = content.find(end_str, start_idx)
    
    if start_idx != -1 and end_idx != -1:
        part1 = content[:start_idx]
        part2 = correct_rows
        part3 = content[end_idx:]
        content = part1 + part2 + part3

    # Fix resource summary table endpoint counts manually
    content = content.replace("<td>RFQ</td>\n            <td>6</td>", "<td>RFQ</td>\n            <td>7</td>")
    content = content.replace("<td>Reminder</td>\n            <td>6</td>", "<td>Reminder</td>\n            <td>7</td>")

    # Fix the endpoint headers counts up above inside the HTML
    content = content.replace("<h3>RFQ</h3><span class=\"count-badge\">6</span>", "<h3>RFQ</h3><span class=\"count-badge\">7</span>")
    content = content.replace("<h3>Reminder</h3><span class=\"count-badge\">6</span>", "<h3>Reminder</h3><span class=\"count-badge\">7</span>")
    content = content.replace("<h3>File</h3><span class=\"count-badge\">2</span>", "<h3>File</h3><span class=\"count-badge\">3</span>")

    # Mark rfq_history and stage_field_value as dormant in API contract 9 tables table
    # rfq_history
    content = content.replace(
        "<td>rfq_history</td>\n            <td>Action audit trail</td>\n            <td><code>rfq_id</code>, <code>entity_type</code>",
        "<td>rfq_history</td>\n            <td>Action audit trail <span class=\"tag-removed\">Dormant</span></td>\n            <td><code>rfq_id</code>, <code>entity_type</code>"
    )
    # rfq_stage_field_value
    content = content.replace(
        "<td>rfq_stage_field_value</td>\n            <td>Schema-less data per stage form</td>\n            <td><code>rfq_stage_id</code>",
        "<td>rfq_stage_field_value</td>\n            <td>Schema-less data per stage form <span class=\"tag-removed\">Dormant</span></td>\n            <td><code>rfq_stage_id</code>"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    fix_html_table()
    print("HTML contract endpoints and dormant statuses fixed successfully!")

# Macro Understanding Rerun Comparison

Generated: 2026-07-02T22:31:53.045Z
Document: Pop Creations Flow 12112025 (1).png (9d09fa89-3a46-465e-a98b-837287c9e22a)

## Headline
- Old GUI baseline claims: 122
- New post-rerun claims: 241
- Net delta: +119
- Exact summary overlap: 6
- Old-only summaries: 116
- New-only summaries: 235
- Normalized quote overlap: 32 of old 66 / new 56 unique quotes

## Extraction Job Contribution
- Broad document-ingestion: staged=53, promoted=53, autoApproved=0, rejections=0
- Lens fan-out jobs: 4
- Lens totals: staged=211, promoted=188, autoApproved=6, duplicatesAppended=3, rejections=211

## Old Counts
- approved / process_rule / policy: 1
- pending_review / dependency / observed_practice: 57
- pending_review / exception_rule / observed_practice: 9
- pending_review / process_rule / policy: 55

## New Counts
- approved / dependency / observed_practice: 1
- approved / process_rule / observed_practice: 5
- pending_review / dependency / observed_practice: 49
- pending_review / dependency / policy: 46
- pending_review / exception_rule / observed_practice: 1
- pending_review / process_rule / observed_practice: 139

## Macro/Fanout State
- outline 2b982c56-238c-462c-ac65-6909ac4b63ba: groups=10, group_items=30, macros=0, findings=0, lenses=["handoffs","exceptions_and_workarounds","ownership_and_roles","dependencies_and_sequence","systems_and_data_entry","customer_or_licensor_risk"]
- job document-ingestion / complete: 1
- job document-lens-extraction / complete: 4
- job source-outline / complete: 1

## New-Only Examples
- dependency / observed_practice / pending_review: The Sales team's 'Agenda template/Kick off Meeting' is a prerequisite for the Creative Direction team to 'Create card: Style guides - input for designers'.
  Quote: [White Box: "Agenda template/ Kick off Meeting"] --> [White Box: "Create card: Style guides - input for designers"]
- dependency / observed_practice / pending_review: Following a 'Meeting w Buyer / Trendboards', the Sales team initiates a 'Design Request Format'.
  Quote: [White Box: "Meeting w Buyer / Trendboards"] --> [White Box: "Design Request Format"]
- dependency / observed_practice / pending_review: A 'Call/email from the buyer' triggers the Sales team to create a 'Design Request Format'.
  Quote: [White Box: "Call/email from the buyer"] --> [White Box: "Design Request Format"]
- dependency / observed_practice / pending_review: The 'Design Request Format' from Sales leads to the Creative Direction team's 'Pre-brief design notes + Confirming size' stage.
  Quote: [White Box: "Design Request Format"] --> [White Box: "Pre-brief design notes + Confirming size"]
- dependency / observed_practice / pending_review: The Creative Direction team's 'Create card: Style guides - input for designers' step is followed by the Creative Designers' 'Assets/compositions selection'.
  Quote: [White Box: "Create card: Style guides - input for designers"] --> [White Box: "Assets/ compositions selection"]
- dependency / observed_practice / pending_review: After 'Pre-brief design notes + Confirming size', the Creative Direction team proceeds to 'Brief'.
  Quote: [White Box: "Pre-brief design notes + Confirming size"] --> [White Box: "Brief"]
- dependency / observed_practice / pending_review: The 'Brief' stage is followed by 'Debriefing' within the Creative Direction team.
  Quote: [White Box: "Brief"] --> [White Box: "Debriefing"]
- dependency / observed_practice / pending_review: After 'Debriefing', the Creative Direction team moves to 'Costing sheets approval'.
  Quote: [White Box: "Debriefing"] --> [White Box: "Costing sheets approval"]
- dependency / observed_practice / pending_review: The 'Costing sheets approval' step by Creative Direction leads to 'Costing sheets elaboration' by Technical Designers.
  Quote: [White Box: "Costing sheets approval"] --> [White Box: "Costing sheets elaboration"]
- dependency / observed_practice / pending_review: After 'Costing sheets approval', the Creative Direction team proceeds to 'Designs Approval'.
  Quote: [White Box: "Costing sheets approval"] --> [White Box: "Designs Approval"]
- dependency / observed_practice / pending_review: After 'Upload to DFlow RFQ code', the Sourcing team sends an 'RFQ to Factories'.
  Quote: [White Box: "Upload to DFlow RFQ code"] --> [White Box: "RFQ to Factories"]
- dependency / observed_practice / pending_review: After sending an 'RFQ to Factories', the Factories provide 'Details and Limitations'.
  Quote: [White Box: "RFQ to Factories"] --> [White Box: "Details and Limitations"]
- dependency / observed_practice / pending_review: The Sourcing team's 'Asking the factories about limitations' step is followed by 'Provide details in Click Up'.
  Quote: [White Box: "Asking the factories about limitations"] --> [White Box: "Provide details in Click Up"]
- dependency / observed_practice / pending_review: After 'Provide details in Click Up', the Factories provide a 'Price'.
  Quote: [White Box: "Provide details in Click Up"] --> [White Box: "Price"]
- dependency / observed_practice / pending_review: If Sales confirms the buyer approves the 'Price', the process moves to 'Designs Approval' by Creative Direction.
  Quote: [White Box: "Price"] --(Arrow: "If Sales confirms buyer approves the Price")--> [White Box: "Designs Approval"]
- dependency / observed_practice / pending_review: After 'Designs Approval' by Creative Direction, the Creative Designers begin 'Design in Progress'.
  Quote: [White Box: "Designs Approval"] --> [White Box: "Design in Progress"]
- dependency / observed_practice / pending_review: After 'Art files in the right format + Packaging' are prepared by Creative Designers, Technical Designers perform 'Tech Packing'.
  Quote: [White Box: "Art files in the right format + Packaging"] --> [White Box: "Tech Packing"]
- dependency / observed_practice / pending_review: After 'Tech Packing' by Technical Designers, the next step is 'Tech Pack Approval'.
  Quote: [White Box: "Tech Packing"] --> [White Box: "Tech Pack Approval"]
- dependency / observed_practice / pending_review: After 'Tech Pack Approval', the Creative Direction team provides 'Tech Pack Submit Authorization'.
  Quote: [White Box: "Tech Pack Approval"] --> [White Box: "Tech Pack Submit Authorization"]
- dependency / observed_practice / pending_review: After 'Tech Pack Submit Authorization' by Creative Direction, the Licensor provides 'Licensor's comment'.
  Quote: [White Box: "Tech Pack Submit Authorization"] --> [White Box: "Licensor's comment"]
- dependency / observed_practice / pending_review: After a 'Tech Pack Update' by Technical Designers, the Creative Direction team provides 'Tech Pack Submit Authorization' again.
  Quote: [White Box: "Tech Pack Update"] --> [White Box: "Tech Pack Submit Authorization"]
- dependency / observed_practice / pending_review: After 'Revisions implementation' by Creative Designers, the process loops back to 'Designs Approval' by Creative Direction.
  Quote: [White Box: "Revisions implementation"] --> [White Box: "Designs Approval"]
- dependency / observed_practice / pending_review: After 'Buyer's Approval', the Sales team sends 'Picks confirmation to PM'.
  Quote: [White Box: "Buyer's Approval"] --> [White Box: "Picks confirmation to PM"]
- dependency / observed_practice / pending_review: After 'Picks confirmation to PM' from Sales, the next step is a 'Sample request'.
  Quote: [White Box: "Picks confirmation to PM"] --> [White Box: "Sample request"]
- dependency / observed_practice / pending_review: After a 'Sample request' from Sales, Junior Designers prepare 'Files for Factory: Art Files + Mock ups+ Packaging + Legal'.
  Quote: [White Box: "Sample request"] --> [White Box: "Files for Factory: Art Files + Mock ups+ Packaging + Legal"]

## Old-Only Examples
- dependency / observed_practice / pending_review: The 'Factory selection' step must occur before 'Buyer's Approval' can be obtained.
  Quote: [Rectangle: "Factory selection"] --> [Rectangle: "Buyer's Approval"]
- dependency / observed_practice / pending_review: Following a 'Meeting w Buyer / Trendboards', a 'Design Request Format' is initiated.
  Quote: [Rectangle: "Meeting w Buyer / Trendboards"] --> [Rectangle: "Design Request Format"]
- dependency / observed_practice / pending_review: A 'Call/email from the buyer' leads to the creation of a 'Design Request Format'.
  Quote: [Rectangle: "Call/email from the buyer"] --> [Rectangle: "Design Request Format"]
- dependency / observed_practice / pending_review: After an 'Agenda template/ Kick off Meeting', the Creative direction team creates a card for 'Style guides - input for designers'.
  Quote: [Rectangle: "Agenda template/ Kick off Meeting"] --> [Rectangle: "Create card: Style guides - input for designers"]
- dependency / observed_practice / pending_review: A 'Design Request Format' leads to 'Pre-brief design notes + Confirming size' by the Creative direction team.
  Quote: [Rectangle: "Design Request Format"] --> [Rectangle: "Pre-brief design notes + Confirming size"]
- dependency / observed_practice / pending_review: After 'Pre-brief design notes + Confirming size', a 'Brief' is created by the Creative direction team.
  Quote: [Rectangle: "Pre-brief design notes + Confirming size"] --> [Rectangle: "Brief"]
- dependency / observed_practice / pending_review: A 'Brief' is followed by a 'Debriefing' by the Creative direction team.
  Quote: [Rectangle: "Brief"] --> [Rectangle: "Debriefing"]
- dependency / observed_practice / pending_review: After 'Debriefing', 'Design in Progress' is initiated by Creative designers.
  Quote: [Rectangle: "Debriefing"] --> [Rectangle: "Design in Progress"]
- dependency / observed_practice / pending_review: 'Costing sheets approval' by Creative direction leads to 'Costing sheets elaboration' by Technical designers.
  Quote: [Rectangle: "Costing sheets approval"] --> [Rectangle: "Costing sheets elaboration"]
- dependency / observed_practice / pending_review: 'Costing sheets approval' by Creative direction also leads to 'Costing sheets/Tech Pack elaboration' by Creative designers.
  Quote: [Rectangle: "Costing sheets approval"] --> [Rectangle: "Costing sheets/Tech Pack elaboration"]
- dependency / observed_practice / pending_review: After 'Costing sheets/Tech Pack elaboration' by Creative designers, the next step is to 'Upload to DFlow RFQ code'.
  Quote: [Rectangle: "Costing sheets/Tech Pack elaboration"] --> [Rectangle: "Upload to DFlow RFQ code"]
- dependency / observed_practice / pending_review: After 'Upload to DFlow RFQ code', 'RFQ to Factories' is sent by Sourcing.
  Quote: [Rectangle: "Upload to DFlow RFQ code"] --> [Rectangle: "RFQ to Factories"]
- dependency / observed_practice / pending_review: After 'RFQ to Factories' is sent, 'Details and Limitations' are provided by the Factories.
  Quote: [Rectangle: "RFQ to Factories"] --> [Rectangle: "Details and Limitations"]
- dependency / observed_practice / pending_review: After 'Details and Limitations' are provided by Factories, Sourcing proceeds to 'Asking the factories about limitations'.
  Quote: [Rectangle: "Details and Limitations"] --> [Rectangle: "Asking the factories about limitations"]
- dependency / observed_practice / pending_review: After 'Asking the factories about limitations', Sourcing must 'Provide details in Click Up'.
  Quote: [Rectangle: "Asking the factories about limitations"] --> [Rectangle: "Provide details in Click Up"]
- dependency / observed_practice / pending_review: After the 'Price' is established, Carlos is responsible for 'SKUs creation (DFlow, ColdLion, MasterData, ClickUp)'.
  Quote: [Rectangle: "Price"] --> [Rectangle: "SKUs creation (DFlow, ColdLion, MasterData, ClickUp)"]
- dependency / observed_practice / pending_review: After 'Create card: Style guides - input for designers', Creative designers perform 'Assets/ compositions selection'.
  Quote: [Rectangle: "Create card: Style guides - input for designers"] --> [Rectangle: "Assets/ compositions selection"]
- dependency / observed_practice / pending_review: After 'Assets/ compositions selection', Creative designers perform 'Costing sheets/Tech Pack elaboration'.
  Quote: [Rectangle: "Assets/ compositions selection"] --> [Rectangle: "Costing sheets/Tech Pack elaboration"]
- dependency / observed_practice / pending_review: After preparing 'Art files in the right format + Packaging', Technical designers perform 'Tech Packing'.
  Quote: [Rectangle: "Art files in the right format + Packaging"] --> [Rectangle: "Tech Packing"]
- dependency / observed_practice / pending_review: After 'Tech Packing', 'Tech Pack Approval' is required by Creative direction.
  Quote: [Rectangle: "Tech Packing"] --> [Rectangle: "Tech Pack Approval"]
- dependency / observed_practice / pending_review: After 'Tech Pack Approval', 'Tech Pack Submit Authorization' is required by Creative direction.
  Quote: [Rectangle: "Tech Pack Approval"] --> [Rectangle: "Tech Pack Submit Authorization"]
- dependency / observed_practice / pending_review: After 'Tech Pack Submit Authorization', the 'Licensor's comment' is received by Creative direction.
  Quote: [Rectangle: "Tech Pack Submit Authorization"] --> [Rectangle: "Licensor's comment"]
- dependency / observed_practice / pending_review: After a 'Tech Pack Update', the process returns to 'Tech Pack Submit Authorization'.
  Quote: [Rectangle: "Tech Pack Update"] --> [Rectangle: "Tech Pack Submit Authorization"]
- dependency / observed_practice / pending_review: After 'Revisions implementation', the process returns to 'Design in Progress'.
  Quote: [Rectangle: "Revisions implementation"] --> [Rectangle: "Design in Progress"]
- dependency / observed_practice / pending_review: After 'Tech Pack Submit Authorization', the Licensing Team performs 'Concept Submit to Licensor'.
  Quote: [Rectangle: "Tech Pack Submit Authorization"] --> [Rectangle: "Concept Submit to Licensor"]
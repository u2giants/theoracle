# New claims after rerun

Exported: 2026-07-02T22:28:21.107Z
Document: Pop Creations Flow 12112025 (1).png (9d09fa89-3a46-465e-a98b-837287c9e22a)
Document status: complete

Total claims: 241

## Counts
- pending_review / dependency / observed_practice: 49
- pending_review / dependency / policy: 46
- pending_review / exception_rule / observed_practice: 1
- pending_review / process_rule / observed_practice: 142
- approved / dependency / observed_practice: 1
- approved / process_rule / observed_practice: 5

## Macro Outline / Fanout
- outline 2b982c56-238c-462c-ac65-6909ac4b63ba: groups=10, group_items=30, macros=0, findings=0, lenses=["handoffs","exceptions_and_workarounds","ownership_and_roles","dependencies_and_sequence","systems_and_data_entry","customer_or_licensor_risk"]

## Jobs
- document-ingestion / complete: 1
- document-lens-extraction / complete: 4
- source-outline / complete: 1

## Claims
### 1. dependency / observed_practice / pending_review
ID: def057a6-e211-48d8-9c68-b54e532c8150
The Sales team's 'Agenda template/Kick off Meeting' is a prerequisite for the Creative Direction team to 'Create card: Style guides - input for designers'.
> [White Box: "Agenda template/ Kick off Meeting"] --> [White Box: "Create card: Style guides - input for designers"]

### 2. dependency / observed_practice / pending_review
ID: 3fa75c57-a295-4d43-8f11-41c1cf4358ee
After a 'Meeting Scheduled' by the Buyer, the Sales team prepares an 'Agenda template/Kick off Meeting'.
> [White Box: "Meeting Scheduled"] --> [White Box: "Agenda template/ Kick off Meeting"]

### 3. dependency / observed_practice / pending_review
ID: da12416a-a5a3-44ca-9242-bf6be9cd0b65
Following a 'Meeting w Buyer / Trendboards', the Sales team initiates a 'Design Request Format'.
> [White Box: "Meeting w Buyer / Trendboards"] --> [White Box: "Design Request Format"]

### 4. dependency / observed_practice / pending_review
ID: e9ada41e-e4a3-4b38-9724-108d51581fa7
A 'Call/email from the buyer' triggers the Sales team to create a 'Design Request Format'.
> [White Box: "Call/email from the buyer"] --> [White Box: "Design Request Format"]

### 5. dependency / observed_practice / pending_review
ID: 7be073b7-97c2-424b-b713-aa65bc5af519
The 'Design Request Format' from Sales leads to the Creative Direction team's 'Pre-brief design notes + Confirming size' stage.
> [White Box: "Design Request Format"] --> [White Box: "Pre-brief design notes + Confirming size"]

### 6. dependency / observed_practice / pending_review
ID: ace8cd05-4ebb-4588-9749-890af6a66006
The Creative Direction team's 'Create card: Style guides - input for designers' step is followed by the Creative Designers' 'Assets/compositions selection'.
> [White Box: "Create card: Style guides - input for designers"] --> [White Box: "Assets/ compositions selection"]

### 7. dependency / observed_practice / pending_review
ID: f82fbd5e-6954-4cd7-aa21-a7fde6ff6fac
After 'Pre-brief design notes + Confirming size', the Creative Direction team proceeds to 'Brief'.
> [White Box: "Pre-brief design notes + Confirming size"] --> [White Box: "Brief"]

### 8. dependency / observed_practice / pending_review
ID: 3bda79ce-cab3-44a7-91c6-ee2e404c0c45
The 'Brief' stage is followed by 'Debriefing' within the Creative Direction team.
> [White Box: "Brief"] --> [White Box: "Debriefing"]

### 9. dependency / observed_practice / pending_review
ID: eb8fb2ab-dc47-4bf9-ab4e-53f4909d6e6c
After 'Debriefing', the Creative Direction team moves to 'Costing sheets approval'.
> [White Box: "Debriefing"] --> [White Box: "Costing sheets approval"]

### 10. dependency / observed_practice / pending_review
ID: 84d97c79-ee7a-460e-907f-cd79b48837a5
The 'Costing sheets approval' step by Creative Direction leads to 'Costing sheets elaboration' by Technical Designers.
> [White Box: "Costing sheets approval"] --> [White Box: "Costing sheets elaboration"]

### 11. dependency / observed_practice / pending_review
ID: dd3da397-da22-43f3-b910-8467b3381261
After 'Costing sheets approval', the Creative Direction team proceeds to 'Designs Approval'.
> [White Box: "Costing sheets approval"] --> [White Box: "Designs Approval"]

### 12. dependency / observed_practice / pending_review
ID: b8e0446c-ad9a-476a-bc8a-8161d2a77ba0
After 'Costing sheets elaboration' by Technical Designers, the next step is to 'Upload to DFlow RFQ code'.
> [White Box: "Costing sheets elaboration"] --> [White Box: "Upload to DFlow RFQ code"]

### 13. dependency / observed_practice / pending_review
ID: 30c55454-316d-4a5e-af7f-807803561ffe
After 'Upload to DFlow RFQ code', the Sourcing team sends an 'RFQ to Factories'.
> [White Box: "Upload to DFlow RFQ code"] --> [White Box: "RFQ to Factories"]

### 14. dependency / observed_practice / pending_review
ID: 38c23d0c-ecb3-4994-86f4-80968c0a271f
After sending an 'RFQ to Factories', the Factories provide 'Details and Limitations'.
> [White Box: "RFQ to Factories"] --> [White Box: "Details and Limitations"]

### 15. dependency / observed_practice / pending_review
ID: 48fb0fed-68b9-44e4-8266-527d8a5c49fe
The Sourcing team's 'Asking the factories about limitations' step is followed by 'Provide details in Click Up'.
> [White Box: "Asking the factories about limitations"] --> [White Box: "Provide details in Click Up"]

### 16. dependency / observed_practice / pending_review
ID: c8656b29-d8bc-4706-9ce2-b8831fc6b9a8
After 'Provide details in Click Up', the Factories provide a 'Price'.
> [White Box: "Provide details in Click Up"] --> [White Box: "Price"]

### 17. dependency / observed_practice / pending_review
ID: e40aea58-1b07-4f97-99a1-8a53c0bb2f1c
If Sales confirms the buyer approves the 'Price', the process moves to 'Designs Approval' by Creative Direction.
> [White Box: "Price"] --(Arrow: "If Sales confirms buyer approves the Price")--> [White Box: "Designs Approval"]

### 18. dependency / observed_practice / pending_review
ID: 4a20c7c2-c34b-4666-81bc-59f6c3a5f002
After 'Designs Approval' by Creative Direction, the Creative Designers begin 'Design in Progress'.
> [White Box: "Designs Approval"] --> [White Box: "Design in Progress"]

### 19. dependency / observed_practice / pending_review
ID: 19d43cd4-5bb2-4b13-b26e-7b29dbea2069
After 'Design in Progress', Creative Designers update the 'DFlow Library + Reference number in PPT'.
> [White Box: "Design in Progress"] --> [White Box: "DFlow Library + Reference number in PPT"]

### 20. dependency / observed_practice / pending_review
ID: 866b6b18-34f7-4f21-bffa-aa8766947285
After updating the 'DFlow Library + Reference number in PPT', Creative Designers prepare 'Art files in the right format + Packaging'.
> [White Box: "DFlow Library + Reference number in PPT"] --> [White Box: "Art files in the right format + Packaging"]

### 21. dependency / observed_practice / pending_review
ID: 7456ef6a-eb3f-4357-8428-7cad4cddd0af
After 'Art files in the right format + Packaging' are prepared by Creative Designers, Technical Designers perform 'Tech Packing'.
> [White Box: "Art files in the right format + Packaging"] --> [White Box: "Tech Packing"]

### 22. dependency / observed_practice / pending_review
ID: 5b30057e-30f6-41bb-bac2-479ed996c2a6
After 'Tech Packing' by Technical Designers, the next step is 'Tech Pack Approval'.
> [White Box: "Tech Packing"] --> [White Box: "Tech Pack Approval"]

### 23. dependency / observed_practice / pending_review
ID: 244e443f-1bc9-457b-bf84-42cdae7a1e3f
After 'Tech Pack Approval', the Creative Direction team provides 'Tech Pack Submit Authorization'.
> [White Box: "Tech Pack Approval"] --> [White Box: "Tech Pack Submit Authorization"]

### 24. dependency / observed_practice / pending_review
ID: 1d05985e-58a7-4e0f-8fc4-29ecc37d95ec
After 'Tech Pack Submit Authorization' by Creative Direction, the Licensor provides 'Licensor's comment'.
> [White Box: "Tech Pack Submit Authorization"] --> [White Box: "Licensor's comment"]

### 25. dependency / observed_practice / pending_review
ID: 27c5f51b-1352-455c-a200-2283844c37f4
After a 'Tech Pack Update' by Technical Designers, the Creative Direction team provides 'Tech Pack Submit Authorization' again.
> [White Box: "Tech Pack Update"] --> [White Box: "Tech Pack Submit Authorization"]

### 26. dependency / observed_practice / pending_review
ID: 47bea457-b661-46fb-be73-da7ac8f7d218
After 'Revisions implementation' by Creative Designers, the process loops back to 'Designs Approval' by Creative Direction.
> [White Box: "Revisions implementation"] --> [White Box: "Designs Approval"]

### 27. dependency / observed_practice / pending_review
ID: e77962d5-a6c8-4d1c-9e07-72e505097428
After 'Buyer's Approval', the Sales team sends 'Picks confirmation to PM'.
> [White Box: "Buyer's Approval"] --> [White Box: "Picks confirmation to PM"]

### 28. dependency / observed_practice / pending_review
ID: 726ed9f3-be17-4d8b-9c9c-43cd2c327c2c
After 'Picks confirmation to PM' from Sales, the next step is a 'Sample request'.
> [White Box: "Picks confirmation to PM"] --> [White Box: "Sample request"]

### 29. dependency / observed_practice / pending_review
ID: 28f73936-7355-48ce-9678-f47d6f1c9de4
After a 'Sample request' from Sales, Junior Designers prepare 'Files for Factory: Art Files + Mock ups+ Packaging + Legal'.
> [White Box: "Sample request"] --> [White Box: "Files for Factory: Art Files + Mock ups+ Packaging + Legal"]

### 30. dependency / observed_practice / pending_review
ID: 44dd0225-f52b-49d3-bba1-97f1da6a8071
After Junior Designers prepare 'Files for Factory: Art Files + Mock ups+ Packaging + Legal', they proceed to 'PPS Audit'.
> [White Box: "Files for Factory: Art Files + Mock ups+ Packaging + Legal"] --> [White Box: "PPS Audit"]

### 31. dependency / observed_practice / pending_review
ID: b0e4c9f5-dc30-4b64-892e-6ba37791d99a
After 'PPS Audit' by Junior Designers, Gina 'Review Audit and send to factory'.
> [White Box: "PPS Audit"] --> [White Box: "Review Audit and send to factory"]

### 32. dependency / observed_practice / pending_review
ID: 161275fc-1834-4bc0-aecd-0212e026afd1
After 'PPS Submit to licensor', the Licensor provides 'PPS Approved'.
> [White Box: "PPS Submit to licensor"] --> [White Box: "PPS Approved"]

### 33. dependency / observed_practice / pending_review
ID: 3572caa8-50d3-4999-8140-0771eecd6160
After Carlos creates a 'Concept image to ColdLion and ClickUp', the Production team handles 'Samples shipped to US'.
> [White Box: "Concept image to ColdLion and ClickUp"] --> [White Box: "Samples shipped to US"]

### 34. dependency / observed_practice / pending_review
ID: 0bf23143-a244-475a-8e2f-1c28b958b7cd
After 'Samples shipped to US', the Buyer provides 'Samples Buyer's approval'.
> [White Box: "Samples shipped to US"] --> [White Box: "Samples Buyer's approval"]

### 35. dependency / observed_practice / pending_review
ID: 3d85799e-c0f7-4890-89fc-95bfd7b64e07
After 'Samples Buyer's approval', the Buyer 'places an order'.
> [White Box: "Samples Buyer's approval"] --> [White Box: "Buyer places an order"]

### 36. dependency / observed_practice / pending_review
ID: 57531157-bc6f-4888-b836-b1ee6b30ed3b
After 'Factory selection' by Albert, the Buyer provides 'Samples Buyer's approval'.
> [White Box: "Factory selection"] --> [White Box: "Samples Buyer's approval"]

### 37. dependency / observed_practice / pending_review
ID: bb3c505b-9455-471b-8bd3-4e3ef82e24c8
After the Licensing Team performs 'Concept Submit to Licensor', the Licensor provides 'Concept Revisions'.
> [White Box: "Concept Submit to Licensor"] --> [White Box: "Concept Revisions"]

### 38. dependency / observed_practice / pending_review
ID: d54a7709-6cd5-45a1-981f-2426680d65e8
After 'Concept Revisions' from the Licensor, the Licensing Team performs a 'Resubmit'.
> [White Box: "Concept Revisions"] --> [White Box: "Resubmit"]

### 39. dependency / observed_practice / pending_review
ID: b0ea3d9c-e5c6-4e48-bb9d-575da70040d5
After a 'Resubmit' by the Licensing Team, the process loops back to 'Concept Submit to Licensor'.
> [White Box: "Resubmit"] --> [White Box: "Concept Submit to Licensor"]

### 40. dependency / observed_practice / pending_review
ID: 59f9f444-d7a2-4ebb-9532-3b2ebf39ce0b
After the Licensor provides 'Concept Approved w comments', the Licensing Team performs 'Comments approval'.
> [White Box: "Concept Approved w comments"] --> [White Box: "Comments approval"]

### 41. dependency / observed_practice / pending_review
ID: facd6a1c-195b-4117-ab6b-9b82282578b5
After 'Comments approval' by the Licensing Team, the Licensor provides 'Concept Approved'.
> [White Box: "Comments approval"] --> [White Box: "Concept Approved"]

### 42. dependency / observed_practice / pending_review
ID: d5554d11-c1c4-4a82-83b2-b2adb45c966d
After 'Concept Approved' by the Licensor, Carlos creates a 'Concept image to ColdLion and ClickUp'.
> [White Box: "Concept Approved"] --> [White Box: "Concept image to ColdLion and ClickUp"]

### 43. dependency / observed_practice / pending_review
ID: 64288efe-b271-4fd7-b943-f787e4d69a4e
After 'Samples Internal Approval' by Creative Direction, Junior Designers perform a 'PPS Audit'.
> [White Box: "Samples Internal Approval"] --> [White Box: "PPS Audit"]

### 44. dependency / observed_practice / pending_review
ID: fd575a2a-58f8-4f7c-a8aa-69ca4488e402
After 'Professional Photos Approval' by Junior Designers, the Production team takes 'Professional Photos'.
> [White Box: "Professional Photos Approval"] --> [White Box: "Professional Photos"]

### 45. dependency / observed_practice / pending_review
ID: 6d202fc8-f0d3-4ead-af42-eabdb0a4b85d
After the Production team takes 'Professional Photos', Carlos handles 'Ship to US'.
> [White Box: "Professional Photos"] --> [White Box: "Ship to US"]

### 46. dependency / observed_practice / pending_review
ID: eafbc9e5-8594-4baf-8f16-36d893a433f2
Design approval proceeds only if Sales confirms the buyer approves the price.
> [White Box: "Price"] --(Arrow: "If Sales confirms buyer approves the Price")--> [White Box: "Designs Approval"]

### 47. dependency / observed_practice / pending_review
ID: 5353b6b5-4dfd-4863-bd14-93e363ac8c6d
Creative Direction's design approval is dependent on Sales confirming the buyer approves the price.
> [White Box: "Price"] --(Arrow: "If Sales confirms buyer approves the Price")--> [White Box: "Designs Approval"]

### 48. dependency / observed_practice / pending_review
ID: df5e9363-127a-4c52-abaa-35d25ad0a033
Creative Direction's design approval is dependent on Sales confirming the buyer approves the price.
> [White Box: "Price"] --(Arrow: "If Sales confirms buyer approves the Price")--> [White Box: "Designs Approval"]

### 49. dependency / observed_practice / pending_review
ID: 2994f39b-ef3c-423d-a41d-03bd59642492
If the audit passes, the PPS is submitted to the licensor.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Pass")--> [White Box: "PPS Submit to licensor"]

### 50. dependency / policy / pending_review
ID: 7568626b-329a-4852-a1ea-e0a9ffc55a8f
After a meeting is scheduled with a buyer, the Sales team must create an agenda template for a kick-off meeting.
> [White Box: "Meeting Scheduled"] --> [White Box: "Agenda template/ Kick off Meeting"]

### 51. dependency / policy / pending_review
ID: bafd0c9f-6fad-40aa-9d29-ce35c2286581
After a meeting with a buyer or trendboards, the Sales team must create a design request format.
> [White Box: "Meeting w Buyer / Trendboards"] --> [White Box: "Design Request Format"]

### 52. dependency / policy / pending_review
ID: 16beb0ae-09bf-45b5-85aa-f74aa3e7a608
A call or email from the buyer triggers the Sales team to create a design request format.
> [White Box: "Call/email from the buyer"] --> [White Box: "Design Request Format"]

### 53. dependency / policy / pending_review
ID: 33af7b17-c374-43bd-b5a1-224eb2d973ae
After the Sales team creates an agenda template for a kick-off meeting, Creative Direction must create a card for style guides as input for designers.
> [White Box: "Agenda template/ Kick off Meeting"] --> [White Box: "Create card: Style guides - input for designers"]

### 54. dependency / policy / pending_review
ID: e9205368-b9fe-4ae2-a6c4-439ce4a6e3d5
After the Sales team creates a design request format, Creative Direction must provide pre-brief design notes and confirm the size.
> [White Box: "Design Request Format"] --> [White Box: "Pre-brief design notes + Confirming size"]

### 55. dependency / policy / pending_review
ID: 370cbcdf-2d41-4d85-b60e-ee1f513a86a0
After Creative Direction creates a card for style guides, Creative Designers must select assets and compositions.
> [White Box: "Create card: Style guides - input for designers"] --> [White Box: "Assets/ compositions selection"]

### 56. dependency / policy / pending_review
ID: 067f5312-ba43-425c-8d2c-06cdf5cd1924
After Creative Direction provides pre-brief design notes and confirms the size, they must create a brief.
> [White Box: "Pre-brief design notes + Confirming size"] --> [White Box: "Brief"]

### 57. dependency / policy / pending_review
ID: 4338c944-2a4b-451f-b6db-afac5dab9dca
After Creative Direction creates a brief, they must conduct a debriefing.
> [White Box: "Brief"] --> [White Box: "Debriefing"]

### 58. dependency / policy / pending_review
ID: 626d83a7-13f5-49b1-a83f-7e3661ad867d
After Creative Direction conducts a debriefing, they must approve costing sheets.
> [White Box: "Debriefing"] --> [White Box: "Costing sheets approval"]

### 59. dependency / policy / pending_review
ID: 160ce36a-523a-4f6a-9491-cad7bec43224
After Creative Direction approves costing sheets, Technical Designers must elaborate on the costing sheets.
> [White Box: "Costing sheets approval"] --> [White Box: "Costing sheets elaboration"]

### 60. dependency / policy / pending_review
ID: 66b045ac-f9f2-4c0b-8fdd-49663fb53375
After Creative Direction approves costing sheets, they must also approve designs.
> [White Box: "Costing sheets approval"] --> [White Box: "Designs Approval"]

### 61. dependency / policy / pending_review
ID: d75605f7-2a38-49d1-8c15-8fd76b1b4934
After Technical Designers elaborate on costing sheets, they must upload them to DFlow with an RFQ code.
> [White Box: "Costing sheets elaboration"] --> [White Box: "Upload to DFlow RFQ code"]

### 62. dependency / policy / pending_review
ID: fa5ca70a-7352-4007-bf43-a1c88eecbe73
After Technical Designers upload costing sheets to DFlow with an RFQ code, Sourcing must send an RFQ to factories.
> [White Box: "Upload to DFlow RFQ code"] --> [White Box: "RFQ to Factories"]

### 63. dependency / policy / pending_review
ID: e0889142-4774-4691-b732-a95b15d3acc2
After Sourcing sends an RFQ to factories, the factories must provide details and limitations.
> [White Box: "RFQ to Factories"] --> [White Box: "Details and Limitations"]

### 64. dependency / policy / pending_review
ID: 2a985600-efd8-45b7-b6d9-6b08d5ac137c
After Sourcing asks factories about limitations, they must provide details in ClickUp.
> [White Box: "Asking the factories about limitations"] --> [White Box: "Provide details in Click Up"]

### 65. dependency / policy / pending_review
ID: e481b54e-5711-4a72-908f-feb8b62062f6
After Sourcing provides details in ClickUp, factories must provide a price.
> [White Box: "Provide details in Click Up"] --> [White Box: "Price"]

### 66. dependency / policy / pending_review
ID: fe272347-cf2a-4094-98a3-2d37d32322f5
If Sales confirms the buyer approves the price, Creative Direction must approve the designs.
> [White Box: "Price"] --(Arrow: "If Sales confirms buyer approves the Price")--> [White Box: "Designs Approval"]

### 67. dependency / policy / pending_review
ID: 6530ba15-f2d3-4ec3-96e1-2dfd737a43c1
After Creative Direction approves designs, Creative Designers must begin design in progress.
> [White Box: "Designs Approval"] --> [White Box: "Design in Progress"]

### 68. dependency / policy / pending_review
ID: a2c5283f-2a63-4326-9389-d0887c3c2b02
After Creative Designers are in design progress, they must update the DFlow Library and add a reference number in PPT.
> [White Box: "Design in Progress"] --> [White Box: "DFlow Library + Reference number in PPT"]

### 69. dependency / policy / pending_review
ID: aab95091-77c1-4ad3-90ca-900a78274eef
After Technical Designers perform tech packing, Creative Direction must approve the tech pack.
> [White Box: "Tech Packing"] --> [White Box: "Tech Pack Approval"]

### 70. dependency / policy / pending_review
ID: dc4f9347-aafa-4447-b41d-b0d70ecc9c9a
After Creative Direction approves the tech pack, they must authorize its submission.
> [White Box: "Tech Pack Approval"] --> [White Box: "Tech Pack Submit Authorization"]

### 71. dependency / policy / pending_review
ID: cbe8f606-f108-4832-967b-de6c930d099f
After Creative Direction authorizes tech pack submission, they must receive licensor comments.
> [White Box: "Tech Pack Submit Authorization"] --> [White Box: "Licensor's comment"]

### 72. dependency / policy / pending_review
ID: 027de992-45df-4620-82be-1caf3058ac10
If a licensor comment is about a legal line or packaging, Technical Designers must update the tech pack.
> [White Box: "Licensor's comment"] --> [White Box: "If comment is legal line or packaging"]

### 73. dependency / policy / pending_review
ID: 08b7403e-8493-4b71-9453-fa0a439669e9
If a licensor comment is about creative design, Creative Designers must implement revisions.
> [White Box: "Licensor's comment"] --> [White Box: "If comment is about creative design"]

### 74. dependency / policy / pending_review
ID: 3be26ea2-0d41-4372-8c7f-855e31ad71f3
After Technical Designers update the tech pack, Creative Direction must re-authorize tech pack submission.
> [White Box: "Tech Pack Update"] --> [White Box: "Tech Pack Submit Authorization"]

### 75. dependency / policy / pending_review
ID: f6e3f417-721e-494f-bd15-7306bbb5ad6b
After Creative Designers implement revisions, Creative Direction must re-approve the designs.
> [White Box: "Revisions implementation"] --> [White Box: "Designs Approval"]

### 76. dependency / policy / pending_review
ID: e54e78bb-4cf8-4a8f-8b0b-c0298b22c4de
After buyer's approval, Sales must confirm picks to the Project Manager.
> [White Box: "Buyer's Approval"] --> [White Box: "Picks confirmation to PM"]

### 77. dependency / policy / pending_review
ID: 1e613127-c27e-445a-941b-8bba1f0b73b1
After Junior Designers conduct a PPS Audit, Gina must review the audit and send it to the factory.
> [White Box: "PPS Audit"] --> [White Box: "Review Audit and send to factory"]

### 78. dependency / policy / pending_review
ID: 0dcf9861-89c7-451e-8d90-d400ca21e560
If the audit passes, Gina must submit the PPS to the licensor.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Pass")--> [White Box: "PPS Submit to licensor"]

### 79. dependency / policy / pending_review
ID: 24a3cc3f-bbfc-4e24-bd9b-f3e4919c786d
If the audit fails, Gina must request re-sampling.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Fail")--> [White Box: "Re-sampling"]

### 80. dependency / policy / pending_review
ID: c712519e-f8a6-46bb-821e-698057f94a3b
After Gina submits the PPS to the licensor, the licensor must approve the PPS.
> [White Box: "PPS Submit to licensor"] --> [White Box: "PPS Approved"]

### 81. dependency / policy / pending_review
ID: c3d47071-f9cb-44ad-a48a-eca8d1c96982
If the PPS is approved for new products, Carlos must create a concept image in ColdLion and ClickUp.
> [White Box: "PPS Approved"] --(Arrow: "For New Products")--> [White Box: "Concept image to ColdLion and ClickUp"]

### 82. dependency / policy / pending_review
ID: 48669594-fd54-4aef-8984-66116e962514
If the PPS is approved for existing products, factories must proceed with mass production.
> [White Box: "PPS Approved"] --(Arrow: "For existing products")--> [White Box: "Mass Production"]

### 83. dependency / policy / pending_review
ID: 527ea3ee-abc4-42ed-85c0-42cb3c250f15
After Carlos creates a concept image in ColdLion and ClickUp, Production must ship samples to the US.
> [White Box: "Concept image to ColdLion and ClickUp"] --> [White Box: "Samples shipped to US"]

### 84. dependency / policy / pending_review
ID: a7ffcede-df29-41a5-b8e8-e5c2121dc41f
After samples are shipped to the US, the buyer must approve the samples.
> [White Box: "Samples shipped to US"] --> [White Box: "Samples Buyer's approval"]

### 85. dependency / policy / pending_review
ID: e4af58c0-ef46-41cd-b1f2-61987a8925f8
After the buyer approves samples, the buyer places an order.
> [White Box: "Samples Buyer's approval"] --> [White Box: "Buyer places an order"]

### 86. dependency / policy / pending_review
ID: c7be75ae-efc6-494c-a84e-6139f3e37107
After Albert selects the factory, the buyer must approve the samples.
> [White Box: "Factory selection"] --> [White Box: "Samples Buyer's approval"]

### 87. dependency / policy / pending_review
ID: 83cc2261-43b6-4a29-8188-ed57cd88c15a
After the Licensing Team submits a concept to the licensor, the licensor may request concept revisions.
> [White Box: "Concept Submit to Licensor"] --> [White Box: "Concept Revisions"]

### 88. dependency / policy / pending_review
ID: 0778173c-5f72-4ae1-b092-f9624eba7ad4
After the licensor requests concept revisions, the Licensing Team must resubmit the concept.
> [White Box: "Concept Revisions"] --> [White Box: "Resubmit"]

### 89. dependency / policy / pending_review
ID: f2f9791c-4899-4a49-8055-34eef5e98d88
After the Licensing Team resubmits a concept, it goes back to the licensor for concept submission.
> [White Box: "Resubmit"] --> [White Box: "Concept Submit to Licensor"]

### 90. dependency / policy / pending_review
ID: b2938bb0-25b3-490e-8d12-ceddd5f6e702
After a concept is approved with comments by the licensor, the Licensing Team must approve the comments.
> [White Box: "Concept Approved w comments"] --> [White Box: "Comments approval"]

### 91. dependency / policy / pending_review
ID: a1def030-12a0-4d2d-8ac6-c4fb567033bd
After the Licensing Team approves comments, the concept is considered approved.
> [White Box: "Comments approval"] --> [White Box: "Concept Approved"]

### 92. dependency / policy / pending_review
ID: dd79ec75-1b07-4c78-b284-c6642dd0c7aa
After a concept is approved, Carlos must create a concept image in ColdLion and ClickUp.
> [White Box: "Concept Approved"] --> [White Box: "Concept image to ColdLion and ClickUp"]

### 93. dependency / policy / pending_review
ID: 2bdfbc2b-1a84-4d0d-bd42-7d110d513667
After Creative Direction provides internal sample approval, Junior Designers must conduct a PPS Audit.
> [White Box: "Samples Internal Approval"] --> [White Box: "PPS Audit"]

### 94. dependency / policy / pending_review
ID: a37f5ae5-640b-484d-9ed5-0a04280e71de
After Junior Designers approve professional photos, Production must take professional photos.
> [White Box: "Professional Photos Approval"] --> [White Box: "Professional Photos"]

### 95. dependency / policy / pending_review
ID: 60fa9f52-fdfd-4bbc-a64b-117477b2f9f1
After Production takes professional photos, Carlos must ship them to the US.
> [White Box: "Professional Photos"] --> [White Box: "Ship to US"]

### 96. exception_rule / observed_practice / pending_review
ID: 18bccc46-e458-4f98-b88a-280f8a944a88
If the audit fails, re-sampling is required.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Fail")--> [White Box: "Re-sampling"]

### 97. process_rule / observed_practice / pending_review
ID: ab350152-1cce-409b-991f-2220b9aac5d9
If the 'Licensor's comment' is about a 'legal line or packaging', the Technical Designers perform a 'Tech Pack Update'.
> [White Box: "Licensor's comment"] --> [White Box: "If comment is legal line or packaging"]

### 98. process_rule / observed_practice / pending_review
ID: 0bf887c9-331b-481a-9ff7-f7e5023f8c39
If the 'Licensor's comment' is 'about creative design', the Creative Designers implement 'Revisions implementation'.
> [White Box: "Licensor's comment"] --> [White Box: "If comment is about creative design"]

### 99. process_rule / observed_practice / pending_review
ID: 656b37d3-c0a4-42ee-8690-186ee0fc64a8
If the 'Audit' passes after Gina reviews it, the Licensing Team performs a 'PPS Submit to licensor'.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Pass")--> [White Box: "PPS Submit to licensor"]

### 100. process_rule / observed_practice / pending_review
ID: 8a0f2756-77e3-429b-8bc7-91d6f818007e
If the 'Audit' fails after Gina reviews it, the process requires 'Re-sampling' by the Factories.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Fail")--> [White Box: "Re-sampling"]

### 101. process_rule / observed_practice / pending_review
ID: 9792693e-8dd4-475a-9bb6-adc01979b63e
If 'PPS Approved' is for 'New Products', Carlos creates a 'Concept image to ColdLion and ClickUp'.
> [White Box: "PPS Approved"] --(Arrow: "For New Products")--> [White Box: "Concept image to ColdLion and ClickUp"]

### 102. process_rule / observed_practice / pending_review
ID: 55cd20d2-ab6a-47f5-8e83-74bf68d118c9
If 'PPS Approved' is for 'existing products', the process moves directly to 'Mass Production' by the Factories.
> [White Box: "PPS Approved"] --(Arrow: "For existing products")--> [White Box: "Mass Production"]

### 103. process_rule / observed_practice / pending_review
ID: bd88abdb-f771-42ed-b862-3f4d1f7a9afe
If the 'Buyer places an order' 'With an Order', Junior Designers prepare 'Files for Factory: Art Files + Mock ups+ Packaging + Legal'.
> [White Box: "Buyer places an order"] --(Arrow: "With an Order")--> [White Box: "Files for Factory: Art Files + Mock ups+ Packaging + Legal"]

### 104. process_rule / observed_practice / pending_review
ID: f296bd93-29a4-4bb7-a16d-5cee4beebc87
If the 'Buyer places an order' 'Before an Order', Albert performs 'Factory selection'.
> [White Box: "Buyer places an order"] --(Arrow: "Before an Order")--> [White Box: "Factory selection"]

### 105. process_rule / observed_practice / pending_review
ID: 6ecf13ab-5014-4714-992e-923befeb1e81
After a meeting with a buyer or trendboards, Sales creates a Design Request Format.
> [White Box: "Meeting w Buyer / Trendboards"] --> [White Box: "Design Request Format"]

### 106. process_rule / observed_practice / pending_review
ID: f7430ae3-ae4e-4b3b-97c4-b279e82ae7bb
A call or email from the buyer triggers the Sales team to create a Design Request Format.
> [White Box: "Call/email from the buyer"] --> [White Box: "Design Request Format"]

### 107. process_rule / observed_practice / pending_review
ID: a8a3afa3-2d53-4516-91d7-6937b455f934
After a meeting is scheduled, Sales creates an Agenda template/Kick off Meeting.
> [White Box: "Meeting Scheduled"] --> [White Box: "Agenda template/ Kick off Meeting"]

### 108. process_rule / observed_practice / pending_review
ID: 54bb9400-f0a4-45c5-9320-1e9ded2603f3
The Creative Direction team creates a card for style guides as input for designers after an Agenda template/Kick off Meeting.
> [White Box: "Agenda template/ Kick off Meeting"] --> [White Box: "Create card: Style guides - input for designers"]

### 109. process_rule / observed_practice / pending_review
ID: e0ea8a3e-6d85-44e0-b981-0fe11337b4a8
The Creative Direction team performs pre-brief design notes and confirms size after receiving a Design Request Format.
> [White Box: "Design Request Format"] --> [White Box: "Pre-brief design notes + Confirming size"]

### 110. process_rule / observed_practice / pending_review
ID: 380b75a4-7e46-474a-853f-d87042696dce
Creative designers select assets and compositions after the Creative Direction team creates a style guide card.
> [White Box: "Create card: Style guides - input for designers"] --> [White Box: "Assets/ compositions selection"]

### 111. process_rule / observed_practice / pending_review
ID: 5dc7c8cd-dbe8-419a-9f2d-88a774be2207
After a meeting is scheduled with the buyer, the Sales team prepares an agenda template for a kick-off meeting.
> [White Box: "Meeting Scheduled"] --> [White Box: "Agenda template/ Kick off Meeting"]

### 112. process_rule / observed_practice / pending_review
ID: a27873c4-3d88-41a3-affa-ab38698f2642
After a meeting is scheduled with a buyer, the Sales team prepares an agenda template for a kick-off meeting.
> [White Box: "Meeting Scheduled"] --> [White Box: "Agenda template/ Kick off Meeting"]

### 113. process_rule / observed_practice / pending_review
ID: 5287f766-dcc7-4869-b7fe-8cab1cc7e29f
The Creative Direction team briefs after pre-brief design notes and size confirmation.
> [White Box: "Pre-brief design notes + Confirming size"] --> [White Box: "Brief"]

### 114. process_rule / observed_practice / pending_review
ID: 06cb58a2-f140-4261-a23f-63e0912ee390
The Creative Direction team debriefs after the brief.
> [White Box: "Brief"] --> [White Box: "Debriefing"]

### 115. process_rule / observed_practice / pending_review
ID: 14dc9876-0db0-4f41-afa4-78ea559cd026
After a meeting with a buyer or trendboards, or a call/email from the buyer, the Sales team creates a Design Request Format.
> [White Box: "Meeting w Buyer / Trendboards"] --> [White Box: "Design Request Format"] [White Box: "Call/email from the buyer"] --> [White Box: "Design Request Format"]

### 116. process_rule / observed_practice / pending_review
ID: a9d22292-765b-48e7-826b-96e88b7d002d
The Creative Direction team approves costing sheets after debriefing.
> [White Box: "Debriefing"] --> [White Box: "Costing sheets approval"]

### 117. process_rule / observed_practice / pending_review
ID: eb3814ec-0bbe-4740-9f07-55d42e0db2ff
Following a kick-off meeting, Creative Direction creates a style guide card as input for designers.
> [White Box: "Agenda template/ Kick off Meeting"] --> [White Box: "Create card: Style guides - input for designers"]

### 118. process_rule / observed_practice / pending_review
ID: 0e4a64d5-92d8-44b0-83ea-222ffcf3fce9
After a design request format is received, Creative Direction prepares pre-brief design notes and confirms sizing.
> [White Box: "Design Request Format"] --> [White Box: "Pre-brief design notes + Confirming size"]

### 119. process_rule / observed_practice / pending_review
ID: 5d284f09-e9f0-42f2-9b6b-660f32eee5d0
Technical designers elaborate costing sheets after Creative Direction approves them.
> [White Box: "Costing sheets approval"] --> [White Box: "Costing sheets elaboration"]

### 120. process_rule / observed_practice / pending_review
ID: b0db7fe4-f346-4e8d-b689-85737c71342c
After a meeting with the buyer and trendboards, the Sales team prepares a design request format.
> [White Box: "Meeting w Buyer / Trendboards"] --> [White Box: "Design Request Format"]

### 121. process_rule / observed_practice / pending_review
ID: 8a1044a8-7da8-4efb-a81b-b3e3afc802b7
The Creative Direction team approves designs after costing sheets are approved.
> [White Box: "Costing sheets approval"] --> [White Box: "Designs Approval"]

### 122. process_rule / observed_practice / pending_review
ID: d0119c04-0dbc-413a-afa5-688382e00060
Creative designers select assets and compositions based on the style guides provided by Creative Direction.
> [White Box: "Create card: Style guides - input for designers"] --> [White Box: "Assets/ compositions selection"]

### 123. process_rule / observed_practice / pending_review
ID: 8f341a26-2c2a-4baa-8de1-22891cd11f3b
After pre-brief design notes and size confirmation, Creative Direction conducts a brief.
> [White Box: "Pre-brief design notes + Confirming size"] --> [White Box: "Brief"]

### 124. process_rule / observed_practice / pending_review
ID: 830f616a-fe11-4727-811d-d7ca0ab89c21
Technical designers upload to DFlow RFQ code after costing sheets elaboration.
> [White Box: "Costing sheets elaboration"] --> [White Box: "Upload to DFlow RFQ code"]

### 125. process_rule / observed_practice / pending_review
ID: 3101ef42-d627-475c-b31b-2563a5d267ec
Sourcing sends an RFQ to factories after the DFlow RFQ code is uploaded.
> [White Box: "Upload to DFlow RFQ code"] --> [White Box: "RFQ to Factories"]

### 126. process_rule / observed_practice / pending_review
ID: d5bb8dc9-63dd-498e-97db-ece09b0f50dd
Following a brief, Creative Direction conducts a debriefing.
> [White Box: "Brief"] --> [White Box: "Debriefing"]

### 127. process_rule / observed_practice / pending_review
ID: c74e0d19-e986-4f34-8d30-acf34b0b8b36
After debriefing, Creative Direction approves costing sheets.
> [White Box: "Debriefing"] --> [White Box: "Costing sheets approval"]

### 128. process_rule / observed_practice / pending_review
ID: 64fca10c-209c-4825-bf11-0d9ef4b4d4ab
Factories provide details and limitations after receiving an RFQ.
> [White Box: "RFQ to Factories"] --> [White Box: "Details and Limitations"]

### 129. process_rule / observed_practice / pending_review
ID: e450b59d-b233-49f1-9e83-816b11918ff5
Sourcing provides details in ClickUp after asking factories about limitations.
> [White Box: "Asking the factories about limitations"] --> [White Box: "Provide details in Click Up"]

### 130. process_rule / observed_practice / pending_review
ID: 060733f4-8f52-49b4-94f9-c5898bbb77fb
After costing sheets are approved, Technical Designers elaborate on the costing sheets.
> [White Box: "Costing sheets approval"] --> [White Box: "Costing sheets elaboration"]

### 131. process_rule / observed_practice / pending_review
ID: 96868b25-be9e-4129-8d33-7991da6366ad
Factories provide pricing after Sourcing provides details in ClickUp.
> [White Box: "Provide details in Click Up"] --> [White Box: "Price"]

### 132. process_rule / observed_practice / pending_review
ID: 05c7d751-ed0c-46d4-aa71-719a46f0fb1f
After costing sheets are approved, Creative Direction also approves designs.
> [White Box: "Costing sheets approval"] --> [White Box: "Designs Approval"]

### 133. process_rule / observed_practice / pending_review
ID: ef84ef3c-96b0-4ff7-8c58-a81bddbd9b2e
A call or email from the buyer triggers the Sales team to prepare a design request format.
> [White Box: "Call/email from the buyer"] --> [White Box: "Design Request Format"]

### 134. process_rule / observed_practice / pending_review
ID: cb01c107-fdc8-4ac2-b2c4-8b56f08a9fef
After costing sheets elaboration, Technical Designers upload to DFlow with an RFQ code.
> [White Box: "Costing sheets elaboration"] --> [White Box: "Upload to DFlow RFQ code"]

### 135. process_rule / observed_practice / pending_review
ID: ab4a6044-19be-4411-923d-2495a5ac313a
Creative designers work on 'Design in Progress' after designs are approved.
> [White Box: "Designs Approval"] --> [White Box: "Design in Progress"]

### 136. process_rule / observed_practice / pending_review
ID: ac38efb6-d5c1-41cc-8496-4e72dfb9fb65
After the Sales team prepares an agenda template for a kick-off meeting, Creative Direction creates a card for style guides as input for designers.
> [White Box: "Agenda template/ Kick off Meeting"] --> [White Box: "Create card: Style guides - input for designers"]

### 137. process_rule / observed_practice / pending_review
ID: 486ba67d-c57a-4b56-b998-dc40bee08b32
After uploading to DFlow with an RFQ code, Sourcing sends an RFQ to factories.
> [White Box: "Upload to DFlow RFQ code"] --> [White Box: "RFQ to Factories"]

### 138. process_rule / observed_practice / pending_review
ID: 318adef9-802d-47c8-81f9-272e13e9473a
After the Sales team prepares a design request format, Creative Direction pre-briefs design notes and confirms the size.
> [White Box: "Design Request Format"] --> [White Box: "Pre-brief design notes + Confirming size"]

### 139. process_rule / observed_practice / pending_review
ID: c98a3a3e-aefe-4c4f-8bfc-f4638aad77f7
Creative designers update the DFlow Library and add a reference number in PPT after 'Design in Progress'.
> [White Box: "Design in Progress"] --> [White Box: "DFlow Library + Reference number in PPT"]

### 140. process_rule / observed_practice / pending_review
ID: d6f01932-eefe-4598-adcf-ec9bc0407fbd
After Sourcing sends an RFQ to factories, factories provide details and limitations.
> [White Box: "RFQ to Factories"] --> [White Box: "Details and Limitations"]

### 141. process_rule / observed_practice / pending_review
ID: a0676de6-7a41-4f99-ac56-cd628a5e6978
After Creative Direction creates a card for style guides, Creative Designers select assets and compositions.
> [White Box: "Create card: Style guides - input for designers"] --> [White Box: "Assets/ compositions selection"]

### 142. process_rule / observed_practice / pending_review
ID: 04445a74-57d8-40b4-ae08-d0bf83f0b49a
After Sourcing asks factories about limitations, Sourcing provides details in ClickUp.
> [White Box: "Asking the factories about limitations"] --> [White Box: "Provide details in Click Up"]

### 143. process_rule / observed_practice / pending_review
ID: 6e7d01ab-aad1-4686-a737-17b09fbe0c6d
After Creative Direction pre-briefs design notes and confirms size, they proceed to the brief stage.
> [White Box: "Pre-brief design notes + Confirming size"] --> [White Box: "Brief"]

### 144. process_rule / observed_practice / pending_review
ID: 5e534c61-3925-4c48-898b-ca12c4706d7b
After the brief, Creative Direction conducts a debriefing.
> [White Box: "Brief"] --> [White Box: "Debriefing"]

### 145. process_rule / observed_practice / pending_review
ID: 34293bec-6e54-4cb3-9944-9da49855a06a
Tech Pack Approval occurs after Tech Packing is completed.
> [White Box: "Tech Packing"] --> [White Box: "Tech Pack Approval"]

### 146. process_rule / observed_practice / pending_review
ID: 31259491-3cbb-4f42-a7f4-e775c0e4c2aa
After debriefing, Creative Direction approves costing sheets.
> [White Box: "Debriefing"] --> [White Box: "Costing sheets approval"]

### 147. process_rule / observed_practice / pending_review
ID: 93e17a8d-badc-48e6-9972-3845b88a8cd1
After Sourcing provides details in ClickUp, factories provide a price.
> [White Box: "Provide details in Click Up"] --> [White Box: "Price"]

### 148. process_rule / observed_practice / pending_review
ID: 4174d792-d8ce-4559-8955-f100eed9f3bf
Tech Pack Submit Authorization occurs after Tech Pack Approval.
> [White Box: "Tech Pack Approval"] --> [White Box: "Tech Pack Submit Authorization"]

### 149. process_rule / observed_practice / pending_review
ID: 62554488-3d20-41dd-88d6-0334b9976635
After Creative Direction approves costing sheets, Technical Designers elaborate on the costing sheets.
> [White Box: "Costing sheets approval"] --> [White Box: "Costing sheets elaboration"]

### 150. process_rule / observed_practice / pending_review
ID: 8f5951bc-74d0-4870-8f6a-b40a0f828b54
Licensor's comments are received after Tech Pack Submit Authorization.
> [White Box: "Tech Pack Submit Authorization"] --> [White Box: "Licensor's comment"]

### 151. process_rule / observed_practice / pending_review
ID: 577a744f-4a30-49e8-87f5-62cf84452d59
After Creative Direction approves costing sheets, they also approve designs.
> [White Box: "Costing sheets approval"] --> [White Box: "Designs Approval"]

### 152. process_rule / observed_practice / pending_review
ID: 31ce0a73-859c-4a93-82b1-b490eb4adc5d
If a licensor's comment is about a legal line or packaging, a Tech Pack Update is performed.
> [White Box: "Licensor's comment"] --> [White Box: "If comment is legal line or packaging"]

### 153. process_rule / observed_practice / pending_review
ID: bfcc002f-97e6-4256-ae7e-c58433b9c6ef
After designs are approved, Creative designers begin design in progress.
> [White Box: "Designs Approval"] --> [White Box: "Design in Progress"]

### 154. process_rule / observed_practice / pending_review
ID: fd80a87e-812e-43f6-9fe0-c80eec283755
After Technical Designers elaborate on costing sheets, they upload to DFlow with an RFQ code.
> [White Box: "Costing sheets elaboration"] --> [White Box: "Upload to DFlow RFQ code"]

### 155. process_rule / observed_practice / pending_review
ID: bfad462c-cc7a-4fc9-b5aa-0a14c16d2cb1
If a licensor's comment is about creative design, revisions are implemented.
> [White Box: "Licensor's comment"] --> [White Box: "If comment is about creative design"]

### 156. process_rule / observed_practice / pending_review
ID: 138c30db-2916-4880-9f81-2e228deab1e4
After uploading to DFlow with an RFQ code, a Request for Quote (RFQ) is sent to factories.
> [White Box: "Upload to DFlow RFQ code"] --> [White Box: "RFQ to Factories"]

### 157. process_rule / observed_practice / pending_review
ID: c181c5a7-398a-4cf1-b5b6-bcd91e73ca52
A Tech Pack Update leads to another Tech Pack Submit Authorization.
> [White Box: "Tech Pack Update"] --> [White Box: "Tech Pack Submit Authorization"]

### 158. process_rule / observed_practice / pending_review
ID: 56349921-2005-4b68-ac72-f6a058e8c545
After an RFQ is sent to factories, factories provide details and limitations.
> [White Box: "RFQ to Factories"] --> [White Box: "Details and Limitations"]

### 159. process_rule / observed_practice / pending_review
ID: 56b2b35c-6112-4bf6-911f-18c12c17c68e
Revisions implementation leads to Designs Approval.
> [White Box: "Revisions implementation"] --> [White Box: "Designs Approval"]

### 160. process_rule / observed_practice / pending_review
ID: 69d442a6-c38f-4d41-bd25-9def907360e4
After Sourcing asks factories about limitations, they provide details in ClickUp.
> [White Box: "Asking the factories about limitations"] --> [White Box: "Provide details in Click Up"]

### 161. process_rule / observed_practice / pending_review
ID: 166ccae4-1fcf-4a56-b1a3-e93a61bef076
After design is in progress, Creative designers upload to DFlow Library and add a reference number in PPT.
> [White Box: "Design in Progress"] --> [White Box: "DFlow Library + Reference number in PPT"]

### 162. process_rule / observed_practice / pending_review
ID: 2ac5269f-86e1-4b3e-9051-fff3f3377bff
Sales confirms picks to the Project Manager after buyer's approval.
> [White Box: "Buyer's Approval"] --> [White Box: "Picks confirmation to PM"]

### 163. process_rule / observed_practice / pending_review
ID: 880168cc-3df7-481a-b1a2-e8ef1836bd89
After Sourcing provides details in ClickUp, factories provide a price.
> [White Box: "Provide details in Click Up"] --> [White Box: "Price"]

### 164. process_rule / observed_practice / pending_review
ID: 107439a3-15bc-4d45-8098-e0f09dca1e97
Sales requests samples after picks confirmation to the Project Manager.
> [White Box: "Picks confirmation to PM"] --> [White Box: "Sample request"]

### 165. process_rule / observed_practice / pending_review
ID: 60e7608d-3233-4943-a763-f219153b72c0
After tech packing, a Tech Pack Approval is required.
> [White Box: "Tech Packing"] --> [White Box: "Tech Pack Approval"]

### 166. process_rule / observed_practice / pending_review
ID: 8ab657a1-b1de-4013-86ac-64632bd8da59
After Creative Direction approves designs, Creative Designers begin design in progress.
> [White Box: "Designs Approval"] --> [White Box: "Design in Progress"]

### 167. process_rule / observed_practice / pending_review
ID: e5fa67ac-959d-4afd-8000-aa886c3fe3a7
After Tech Pack Approval, a Tech Pack Submit Authorization is required.
> [White Box: "Tech Pack Approval"] --> [White Box: "Tech Pack Submit Authorization"]

### 168. process_rule / observed_practice / pending_review
ID: 0b8d8fb6-1188-4581-b290-ef84eace06c1
Gina reviews the audit and sends it to the factory after a PPS Audit.
> [White Box: "PPS Audit"] --> [White Box: "Review Audit and send to factory"]

### 169. process_rule / observed_practice / pending_review
ID: 3fe4b5c9-fe3c-4e69-9a64-5c9ca93ba315
After Tech Pack Submit Authorization, a licensor's comment is received.
> [White Box: "Tech Pack Submit Authorization"] --> [White Box: "Licensor's comment"]

### 170. process_rule / observed_practice / pending_review
ID: 2e4a42e0-df5b-47a1-94d7-7010cf0e8a50
After Technical Designers perform tech packing, they submit for tech pack approval.
> [White Box: "Tech Packing"] --> [White Box: "Tech Pack Approval"]

### 171. process_rule / observed_practice / pending_review
ID: 443373b1-89d0-4a43-83bc-63f9d89b6b02
After a Tech Pack Update, a Tech Pack Submit Authorization is required.
> [White Box: "Tech Pack Update"] --> [White Box: "Tech Pack Submit Authorization"]

### 172. process_rule / observed_practice / pending_review
ID: 7de4e096-10bf-4f41-9b54-3c4c1b6a1cf3
The PPS is approved after submission to the licensor.
> [White Box: "PPS Submit to licensor"] --> [White Box: "PPS Approved"]

### 173. process_rule / observed_practice / pending_review
ID: 826d6587-a8cb-4c3c-8992-297e319867e1
After tech pack approval, Creative Direction authorizes tech pack submission.
> [White Box: "Tech Pack Approval"] --> [White Box: "Tech Pack Submit Authorization"]

### 174. process_rule / observed_practice / pending_review
ID: a41d792a-5046-4a7f-ab82-1605d9af10a8
After revisions are implemented, designs require approval again.
> [White Box: "Revisions implementation"] --> [White Box: "Designs Approval"]

### 175. process_rule / observed_practice / pending_review
ID: 0dd26224-8ba9-4cc2-bc6e-f54d2fa59679
For new products, Carlos creates a concept image in ColdLion and ClickUp after PPS approval.
> [White Box: "PPS Approved"] --(Arrow: "For New Products")--> [White Box: "Concept image to ColdLion and ClickUp"]

### 176. process_rule / observed_practice / pending_review
ID: 462196be-bae3-407f-989b-e3f7fbcc2501
After tech pack submission authorization, Creative Direction receives licensor comments.
> [White Box: "Tech Pack Submit Authorization"] --> [White Box: "Licensor's comment"]

### 177. process_rule / observed_practice / pending_review
ID: 5d541508-23f0-4c82-9e61-8e6430d72093
After buyer's approval, Sales confirms picks to the PM.
> [White Box: "Buyer's Approval"] --> [White Box: "Picks confirmation to PM"]

### 178. process_rule / observed_practice / pending_review
ID: 73e44fd7-cdd7-45ca-a025-f582f6c34b51
After picks confirmation to the PM, Sales requests a sample.
> [White Box: "Picks confirmation to PM"] --> [White Box: "Sample request"]

### 179. process_rule / observed_practice / pending_review
ID: bad2725e-d5e6-45f4-a891-cb9b3d3f2d11
If a licensor comment is about a legal line or packaging, Technical Designers update the tech pack.
> [White Box: "If comment is legal line or packaging"] --> [White Box: "Tech Pack Update"]

### 180. process_rule / observed_practice / pending_review
ID: c25974ac-7ca8-4126-b6cb-a8efe93d91c8
Samples are shipped to the US after the concept image is uploaded to ColdLion and ClickUp.
> [White Box: "Concept image to ColdLion and ClickUp"] --> [White Box: "Samples shipped to US"]

### 181. process_rule / observed_practice / pending_review
ID: c05a77f1-5520-40e5-9525-b34af41cac63
If a licensor comment is about creative design, Creative Designers implement revisions.
> [White Box: "If comment is about creative design"] --> [White Box: "Revisions implementation"]

### 182. process_rule / observed_practice / pending_review
ID: fc681fa0-e27f-4ee1-bdd4-52992dc6066e
Buyer's approval of samples occurs after samples are shipped to the US.
> [White Box: "Samples shipped to US"] --> [White Box: "Samples Buyer's approval"]

### 183. process_rule / observed_practice / pending_review
ID: b5d21f74-091c-45f5-b7bc-0996da0167aa
After a tech pack update, Creative Direction authorizes tech pack submission again.
> [White Box: "Tech Pack Update"] --> [White Box: "Tech Pack Submit Authorization"]

### 184. process_rule / observed_practice / pending_review
ID: 39915ba5-a32e-4aab-be4a-c548f4a9ef6f
After files are prepared for the factory, a PPS Audit is conducted.
> [White Box: "Files for Factory: Art Files + Mock ups+ Packaging + Legal"] --> [White Box: "PPS Audit"]

### 185. process_rule / observed_practice / pending_review
ID: 3f7ccb48-3aa8-4369-968f-0fccd0e7fbd4
A buyer places an order after samples are approved by the buyer.
> [White Box: "Samples Buyer's approval"] --> [White Box: "Buyer places an order"]

### 186. process_rule / observed_practice / pending_review
ID: 1aca4d61-524f-45a3-805f-643a8b728f39
After revisions implementation, Creative Direction approves designs again.
> [White Box: "Revisions implementation"] --> [White Box: "Designs Approval"]

### 187. process_rule / observed_practice / pending_review
ID: d1345b09-a213-41a3-9c7b-3288487cacd1
After a PPS Audit, Gina reviews the audit and sends it to the factory.
> [White Box: "PPS Audit"] --> [White Box: "Review Audit and send to factory"]

### 188. process_rule / observed_practice / pending_review
ID: eecbcefb-c49f-46ef-a574-c4cc0b0f8e43
After buyer's approval, Sales sends picks confirmation to the Project Manager (PM).
> [White Box: "Buyer's Approval"] --> [White Box: "Picks confirmation to PM"]

### 189. process_rule / observed_practice / pending_review
ID: 440867bc-f3c3-46fb-a4e8-023ab74519d5
If the audit passes, the PPS is submitted to the licensor.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Pass")--> [White Box: "PPS Submit to licensor"]

### 190. process_rule / observed_practice / pending_review
ID: ce2d069b-ae27-4d46-95a3-b9cce9bb3951
After picks confirmation to the PM, Sales sends a sample request.
> [White Box: "Picks confirmation to PM"] --> [White Box: "Sample request"]

### 191. process_rule / observed_practice / pending_review
ID: 5eef0d2b-ea56-4fc2-8c93-bfa91295bfa0
If there is no order, factory selection occurs before a buyer places an order.
> [White Box: "Buyer places an order"] --(Arrow: "Before an Order")--> [White Box: "Factory selection"]

### 192. process_rule / observed_practice / pending_review
ID: c47dade2-6459-4059-851f-849459653275
After a sample request, Junior Designers prepare art files, mock-ups, packaging, and legal documents for the factory.
> [White Box: "Sample request"] --> [White Box: "Files for Factory: Art Files + Mock ups+ Packaging + Legal"]

### 193. process_rule / observed_practice / pending_review
ID: 93b53cc5-8366-481c-ac6b-9617c75e05b7
Buyer's approval of samples occurs after factory selection.
> [White Box: "Factory selection"] --> [White Box: "Samples Buyer's approval"]

### 194. process_rule / observed_practice / pending_review
ID: daff8da0-c04d-44ce-ad54-acdee3bbe067
After PPS is submitted to the licensor, the PPS is approved.
> [White Box: "PPS Submit to licensor"] --> [White Box: "PPS Approved"]

### 195. process_rule / observed_practice / pending_review
ID: 54b43e2f-a3c5-48ef-ac73-e503238b1498
The Licensing Team submits concepts to the licensor, which can lead to concept revisions.
> [White Box: "Concept Submit to Licensor"] --> [White Box: "Concept Revisions"]

### 196. process_rule / observed_practice / pending_review
ID: 7006b71b-2453-4456-bd57-982f63bec313
After preparing files for the factory, Junior Designers conduct a PPS Audit.
> [White Box: "Files for Factory: Art Files + Mock ups+ Packaging + Legal"] --> [White Box: "PPS Audit"]

### 197. process_rule / observed_practice / pending_review
ID: aa674c12-ccd3-4941-8ebd-08d8c178873f
Concept revisions lead to resubmission to the licensor.
> [White Box: "Concept Revisions"] --> [White Box: "Resubmit"]

### 198. process_rule / observed_practice / pending_review
ID: eb1a5f9f-40e7-4b6b-8761-e7fb49646392
For new products, after PPS is approved, Carlos creates a concept image in ColdLion and ClickUp.
> [White Box: "PPS Approved"] --(Arrow: "For New Products")--> [White Box: "Concept image to ColdLion and ClickUp"]

### 199. process_rule / observed_practice / pending_review
ID: da3e878d-57f7-4cf9-87dd-1e7e4159c4c6
If the audit passes, Gina submits the PPS to the licensor.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Pass")--> [White Box: "PPS Submit to licensor"]

### 200. process_rule / observed_practice / pending_review
ID: 4b93c4e4-64b5-4b4b-b1e9-bb8d866c825f
Resubmission leads to another concept submission to the licensor.
> [White Box: "Resubmit"] --> [White Box: "Concept Submit to Licensor"]

### 201. process_rule / observed_practice / pending_review
ID: a0b954c9-75bd-4211-9292-8409a19e2101
For existing products, after PPS is approved, mass production begins.
> [White Box: "PPS Approved"] --(Arrow: "For existing products")--> [White Box: "Mass Production"]

### 202. process_rule / observed_practice / pending_review
ID: f9de1e91-15e5-4adb-8c51-c5ad399378ed
If the audit fails, factories perform re-sampling.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Fail")--> [White Box: "Re-sampling"]

### 203. process_rule / observed_practice / pending_review
ID: 605e0e9e-e3b6-48c6-bfb1-85f61aef4282
After PPS is submitted to the licensor, the licensor approves the PPS.
> [White Box: "PPS Submit to licensor"] --> [White Box: "PPS Approved"]

### 204. process_rule / observed_practice / pending_review
ID: 98054f23-5403-45ba-b64c-f959894e2c31
If PPS is approved for new products, Carlos uploads the concept image to ColdLion and ClickUp.
> [White Box: "PPS Approved"] --(Arrow: "For New Products")--> [White Box: "Concept image to ColdLion and ClickUp"]

### 205. process_rule / observed_practice / pending_review
ID: eef65ba7-7aa4-4c8a-b91b-47fae436a992
Carlos uploads the concept image to ColdLion and ClickUp after concept approval.
> [White Box: "Concept Approved"] --> [White Box: "Concept image to ColdLion and ClickUp"]

### 206. process_rule / observed_practice / pending_review
ID: e2a0ea76-6a69-4631-b52a-65a74f342036
After a concept image is created in ColdLion and ClickUp, samples are shipped to the US.
> [White Box: "Concept image to ColdLion and ClickUp"] --> [White Box: "Samples shipped to US"]

### 207. process_rule / observed_practice / pending_review
ID: ed3d2347-80a0-48e4-9f80-e002d5c34371
If PPS is approved for existing products, factories proceed to mass production.
> [White Box: "PPS Approved"] --(Arrow: "For existing products")--> [White Box: "Mass Production"]

### 208. process_rule / observed_practice / pending_review
ID: 153296f8-081c-4365-bdd9-6239729e4101
After samples are shipped to the US, the buyer's approval of samples is obtained.
> [White Box: "Samples shipped to US"] --> [White Box: "Samples Buyer's approval"]

### 209. process_rule / observed_practice / pending_review
ID: 02bd7f12-e9e3-4731-873b-0fd8dc6ec29c
After Carlos uploads the concept image to ColdLion and ClickUp, samples are shipped to the US.
> [White Box: "Concept image to ColdLion and ClickUp"] --> [White Box: "Samples shipped to US"]

### 210. process_rule / observed_practice / pending_review
ID: 11fafe03-07c9-4376-9795-906874ef9a32
After samples receive buyer's approval, the buyer places an order.
> [White Box: "Samples Buyer's approval"] --> [White Box: "Buyer places an order"]

### 211. process_rule / observed_practice / pending_review
ID: 9f4f9f21-4f57-48c9-b4a1-7ea1a90e4650
After samples are shipped to the US, the buyer approves the samples.
> [White Box: "Samples shipped to US"] --> [White Box: "Samples Buyer's approval"]

### 212. process_rule / observed_practice / pending_review
ID: 819fec49-e5a1-49e6-b127-5c4334b62dcc
Carlos ships to the US after professional photos are taken.
> [White Box: "Professional Photos"] --> [White Box: "Ship to US"]

### 213. process_rule / observed_practice / pending_review
ID: 2e4bda2d-f18f-47f4-8127-3b27ca99ab09
After samples are approved by the buyer, the buyer places an order.
> [White Box: "Samples Buyer's approval"] --> [White Box: "Buyer places an order"]

### 214. process_rule / observed_practice / pending_review
ID: 47996558-8281-4617-9802-d0385a60d6dd
If there is no order yet, but a buyer places an order, factory selection occurs.
> [White Box: "Buyer places an order"] --(Arrow: "Before an Order")--> [White Box: "Factory selection"]

### 215. process_rule / observed_practice / pending_review
ID: af64afe8-4e9b-4924-888b-852ced39f969
If a buyer places an order, Junior Designers prepare art files, mock-ups, packaging, and legal documents for the factory.
> [White Box: "Buyer places an order"] --(Arrow: "With an Order")--> [White Box: "Files for Factory: Art Files + Mock ups+ Packaging + Legal"]

### 216. process_rule / observed_practice / pending_review
ID: b133fc2f-2799-48ed-9245-95b616d6d5d6
After factory selection, samples receive buyer's approval.
> [White Box: "Factory selection"] --> [White Box: "Samples Buyer's approval"]

### 217. process_rule / observed_practice / pending_review
ID: dc5be148-c0a5-4216-b614-d71097a0521c
If a buyer places an order before an actual order, Albert selects the factory.
> [White Box: "Buyer places an order"] --(Arrow: "Before an Order")--> [White Box: "Factory selection"]

### 218. process_rule / observed_practice / pending_review
ID: cdb8e252-400a-4c98-a646-9ef92cb691c6
After a concept is submitted to the licensor, concept revisions are received.
> [White Box: "Concept Submit to Licensor"] --> [White Box: "Concept Revisions"]

### 219. process_rule / observed_practice / pending_review
ID: eed5d746-0bf5-4ad0-8cd3-dc3123e4885d
After factory selection, the buyer approves samples.
> [White Box: "Factory selection"] --> [White Box: "Samples Buyer's approval"]

### 220. process_rule / observed_practice / pending_review
ID: d68f8b62-c198-4584-be2d-6eea906eb887
After concept revisions, the concept is resubmitted.
> [White Box: "Concept Revisions"] --> [White Box: "Resubmit"]

### 221. process_rule / observed_practice / pending_review
ID: 5c3051ff-621f-431b-b0ad-557e3ea1b6c6
After the Licensing Team submits a concept to the licensor, the licensor provides concept revisions.
> [White Box: "Concept Submit to Licensor"] --> [White Box: "Concept Revisions"]

### 222. process_rule / observed_practice / pending_review
ID: 281d49f2-1329-49fe-9c42-32f6d087a3b1
After resubmission, the concept is submitted to the licensor again.
> [White Box: "Resubmit"] --> [White Box: "Concept Submit to Licensor"]

### 223. process_rule / observed_practice / pending_review
ID: 182009ab-b219-4e55-b389-cb0df82c18b1
After concept revisions, the Licensing Team resubmits the concept.
> [White Box: "Concept Revisions"] --> [White Box: "Resubmit"]

### 224. process_rule / observed_practice / pending_review
ID: 96ac82f6-aa70-422d-ba16-f81f40030c49
After a concept is approved with comments, the Licensing Team approves the comments.
> [White Box: "Concept Approved w comments"] --> [White Box: "Comments approval"]

### 225. process_rule / observed_practice / pending_review
ID: 70b5507a-8865-4c29-ae42-b8d38f482fd4
After resubmission, the Licensing Team submits the concept to the licensor again.
> [White Box: "Resubmit"] --> [White Box: "Concept Submit to Licensor"]

### 226. process_rule / observed_practice / pending_review
ID: e47c5dff-62fd-4eff-828c-fc8cd603d3c9
After comments approval, the concept is approved.
> [White Box: "Comments approval"] --> [White Box: "Concept Approved"]

### 227. process_rule / observed_practice / pending_review
ID: e326cdbe-d79c-456e-9e7c-2098938d5792
After a concept is approved, Carlos uploads the concept image to ColdLion and ClickUp.
> [White Box: "Concept Approved"] --> [White Box: "Concept image to ColdLion and ClickUp"]

### 228. process_rule / observed_practice / pending_review
ID: dc499eca-ff07-4898-8842-3463a78618ca
After comments are approved, the concept is approved.
> [White Box: "Comments approval"] --> [White Box: "Concept Approved"]

### 229. process_rule / observed_practice / pending_review
ID: 88a931f8-1ea7-49d9-b1b5-bf5108915548
After Creative Direction's internal samples approval, Junior Designers conduct a PPS Audit.
> [White Box: "Samples Internal Approval"] --> [White Box: "PPS Audit"]

### 230. process_rule / observed_practice / pending_review
ID: 81dcde2b-9683-43c2-a16d-2dd5f25c1eb8
After a concept is approved, Carlos creates a concept image in ColdLion and ClickUp.
> [White Box: "Concept Approved"] --> [White Box: "Concept image to ColdLion and ClickUp"]

### 231. process_rule / observed_practice / pending_review
ID: 2387eab3-f70b-4eec-b0cd-708d7b6ef9be
After professional photos approval, Production takes professional photos.
> [White Box: "Professional Photos Approval"] --> [White Box: "Professional Photos"]

### 232. process_rule / observed_practice / pending_review
ID: 6d867893-1291-4296-9bd6-6b077c00b8d7
After samples receive internal approval, a PPS Audit is conducted.
> [White Box: "Samples Internal Approval"] --> [White Box: "PPS Audit"]

### 233. process_rule / observed_practice / pending_review
ID: 40cc9554-e5e5-4f50-85cc-2b0ed95fbadc
After professional photos are taken, Carlos ships them to the US.
> [White Box: "Professional Photos"] --> [White Box: "Ship to US"]

### 234. process_rule / observed_practice / pending_review
ID: 19ea6103-b916-4bd1-9d76-94e107a87707
After professional photos are approved, professional photos are taken.
> [White Box: "Professional Photos Approval"] --> [White Box: "Professional Photos"]

### 235. process_rule / observed_practice / pending_review
ID: 83fdfaba-f2d9-4ac8-b882-da99b7b69152
After professional photos are taken, Carlos ships to the US.
> [White Box: "Professional Photos"] --> [White Box: "Ship to US"]

### 236. dependency / observed_practice / approved
ID: 72b62b9a-3793-42d7-b941-5933b7ee29a9
If the audit fails, re-sampling is required.
> [White Box: "Review Audit and send to factory"] --(Arrow: "If Audit: Fail")--> [White Box: "Re-sampling"]

### 237. process_rule / observed_practice / approved
ID: 1a82eb35-3bc6-4a2c-8b27-980b1bdb947c
For existing products, mass production begins after PPS approval.
> [White Box: "PPS Approved"] --(Arrow: "For existing products")--> [White Box: "Mass Production"]

### 238. process_rule / observed_practice / approved
ID: bceb4b0c-bcab-4f49-b04b-c148b807aeb5
Comments approval occurs after a concept is approved with comments.
> [White Box: "Concept Approved w comments"] --> [White Box: "Comments approval"]

### 239. process_rule / observed_practice / approved
ID: 6ba77aa0-e28c-4174-94a1-e92be1d07e64
A concept is approved after comments approval.
> [White Box: "Comments approval"] --> [White Box: "Concept Approved"]

### 240. process_rule / observed_practice / approved
ID: dd95e455-7520-41b1-8c76-028fda14dd7c
A PPS Audit occurs after samples receive internal approval.
> [White Box: "Samples Internal Approval"] --> [White Box: "PPS Audit"]

### 241. process_rule / observed_practice / approved
ID: 7c7bdd24-009c-4e6d-9d42-8fab0551131a
Professional photos are taken after professional photos approval.
> [White Box: "Professional Photos Approval"] --> [White Box: "Professional Photos"]

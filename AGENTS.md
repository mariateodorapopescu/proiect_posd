# SecureSync agent instructions

Read `.agents/architecture.md` and `.agents/domain.md` before changes. Also read the matching data-model, integrations, workflows, security and testing notes when relevant.

Keep this project focused on the OAuth 2.0 document-access assignment. Use SecureSync naming and `ro.securesync.api`. Never import application credentials, private data, deployment scripts or unrelated domain features from another repository.

Make focused changes, preserve existing work, add tests for behavior changes and run applicable checks. Update matching `.agents/` and `docs/` contracts in the same change. Report only validation actually executed. Never commit `.env`, tokens, uploaded files or raw experimental data by default.

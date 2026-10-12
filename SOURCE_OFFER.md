# Corresponding source for Oracle users

Owner choice, October 11, 2026 EDT, verbatim from Albert's chat message:
"users may receive it under the library’s licensing terms".

Oracle application source is offered to its authenticated operating-model users under GNU AGPL version 3 or later; see LICENSE. Copyright POP Creations and the respective original contributors. Third-party components retain their own notices and licenses. No license or access restriction is imposed on recipients beyond the applicable license terms. This does not publish company documents, original uploads, credentials, private audit evidence or application data.

The operating-model screen links to its authenticated source-download route. That route offers the exact build's source archive, manifest and build instructions without payment. The archive includes web/worker/Python/package sources, configuration, locked dependency manifests, migrations, source-generation/build scripts, this offer, license and notices. It excludes secrets, uploads, private evidence, environment values, dependencies installed in node_modules and generated deployment outputs. Exact dependency sources/licenses are identified by the locked manifests and third-party notices. The release gate must prove that the archive covers the deployed web and worker versions before any analytical feature is enabled. If build source cannot be packaged, the build fails; no hosted analytical capability is silently served without its offer.

PM4Py remains uninstalled and unbundled pending the independent review of this exact source-delivery arrangement and runtime qualification. The user choice authorizes source delivery; it is not a legal opinion or an independent technical approval.

Build from the unpacked source with Node 24 and pnpm 9.5.0: install the frozen workspace lock, run the recorded verification guards, build the web application, and synchronize the dedicated worker Python bundle. Python uses CPython 3.12.14 and the exact uv lock in services/oracle-brain. Secrets and company data are supplied by the user's own admitted environment, never included in source. SOURCE_ARCHIVE_MANIFEST.json records each included file hash and the exact source revision. See README.md and the included deployment/configuration instructions for the managed-platform topology. CI verifies and does not deploy.

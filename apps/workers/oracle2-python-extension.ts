import type { BuildExtension } from '@trigger.dev/build';
import { addAdditionalFilesToBuild } from '@trigger.dev/build/internal';

// Replaces @trigger.dev/python's install layer, which pins Debian's python3
// (3.11 on bookworm). The Oracle 2 bundle requires 3.12, so install it with
// the same uv release CI uses and hash-checked requirements. runScript reads
// PYTHON_BIN_PATH, so @trigger.dev/python's runtime API is unchanged.
const UV_IMAGE = 'ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424';
export const ORACLE2_PYTHON_VERSION = '3.12.14';

export function oracle2Python(options: {
  scripts: string[];
  requirementsFile: string;
  devPythonBinaryPath: string;
}): BuildExtension {
  return {
    name: 'oracle2-python',
    async onBuildComplete(context, manifest) {
      await addAdditionalFilesToBuild('oracle2-python', { files: options.scripts }, context, manifest);
      if (context.target === 'dev') {
        process.env.PYTHON_BIN_PATH = options.devPythonBinaryPath;
        return;
      }
      await addAdditionalFilesToBuild('oracle2-python', { files: [options.requirementsFile] }, context, manifest);
      context.addLayer({
        id: 'oracle2-python',
        image: {
          instructions: [
            `COPY --from=${UV_IMAGE} /uv /usr/local/bin/uv`,
            'ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python UV_NO_CACHE=1',
            `RUN uv venv --python ${ORACLE2_PYTHON_VERSION} /opt/venv`,
            `COPY ${options.requirementsFile} ./oracle2-requirements.txt`,
            // Every artifact is hash-pinned, so considering both indexes cannot admit a
            // substituted package; uv's default first-index rule rejects certifi etc.
            // because the PyTorch CPU index also carries older copies.
            'RUN uv pip install --python /opt/venv/bin/python --require-hashes --index-strategy unsafe-best-match -r ./oracle2-requirements.txt',
            'RUN /opt/venv/bin/python -c "import sys; assert sys.version_info[:3] == (3, 12, 14), sys.version"',
          ],
        },
        deploy: { env: { PYTHON_BIN_PATH: '/opt/venv/bin/python' }, override: true },
      });
    },
  };
}

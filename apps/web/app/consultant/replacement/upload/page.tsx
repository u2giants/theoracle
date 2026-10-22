import { requireEmployee } from '@/lib/auth-guard';
import OriginalUploadForm from './upload-form';
export const dynamic='force-dynamic';
export default async function OriginalUploadPage(){await requireEmployee();return <main className="mx-auto max-w-xl space-y-4 p-8"><h1 className="text-2xl font-semibold">Upload an original PDF</h1><p>Upload one PDF up to 25 MiB. Uploaded files still need independent reading and review.</p><OriginalUploadForm /></main>;}

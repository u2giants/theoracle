import { requireEmployee } from '../../../../lib/auth-guard';
import { authenticatedModelReviewPageModel } from '../../../../lib/replacement-protected-client';
import ModelReview from './review';
export const dynamic='force-dynamic';
export default async function ReviewPage(){
  const pending=authenticatedModelReviewPageModel();
  await requireEmployee();
  const modelId=await pending;
  return modelId?<ModelReview modelId={modelId}/>:<main><h1>Review documentary accounts</h1><p>Review is unavailable.</p></main>;
}

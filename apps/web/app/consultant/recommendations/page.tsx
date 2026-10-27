import {requireEmployee} from '@/lib/auth-guard';
import {authenticatedRecommendationPageAvailableV1} from '@/lib/replacement-protected-client';
import {RecommendationControlsV1} from './recommendation-controls';
export default async function RecommendationsPage(){
 const available=authenticatedRecommendationPageAvailableV1();
 await requireEmployee();
 return <RecommendationControlsV1 available={await available}/>;
}

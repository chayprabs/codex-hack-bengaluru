import { DashboardPage, LoadingState } from "@/components/dashboard/ui";

export default function Loading() {
  return (
    <DashboardPage
      eyebrow="Shame wall"
      title="Loading the wall"
      description="Fetching the latest findings leaderboard."
    >
      <LoadingState
        title="Preparing the wall"
        description="The frontend is loading audit findings and severity data from the API."
      />
    </DashboardPage>
  );
}

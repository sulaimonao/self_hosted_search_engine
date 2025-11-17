import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const jobs = [
  { id: "3312", type: "Bundle export", status: "Queued", duration: "--" },
  { id: "3311", type: "Repo checks", status: "Running", duration: "00:01:23" },
  { id: "3308", type: "Domain crawl", status: "Completed", duration: "00:12:44" },
];

export function JobsTable() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Jobs</CardTitle>
      </CardHeader>
      <CardContent className="overflow-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-muted-foreground">
              <th className="py-2">Job</th>
              <th className="py-2">Type</th>
              <th className="py-2">Status</th>
              <th className="py-2">Duration</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className="border-t">
                <td className="py-2 font-mono text-xs">#{job.id}</td>
                <td className="py-2">{job.type}</td>
                <td className="py-2">{job.status}</td>
                <td className="py-2">{job.duration}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

import { Suspense } from "react";
import AutomationRunner from "@/components/AutomationRunner";

export default function AutomationPage() {
  return (
    <Suspense
      fallback={
        <div className="container mx-auto max-w-6xl px-4 py-16 text-center text-muted-foreground">
          Loading farm automation…
        </div>
      }
    >
      <AutomationRunner />
    </Suspense>
  );
}

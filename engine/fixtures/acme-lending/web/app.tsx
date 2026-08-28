const API = process.env.NEXT_PUBLIC_API_URL;
const POSTHOG_KEY = process.env.POSTHOG_API_KEY;

export async function submitApplication(payload: unknown) {
  const res = await fetch(`${API}/api/applications`, { method: "POST", body: JSON.stringify(payload) });
  return res.json();
}

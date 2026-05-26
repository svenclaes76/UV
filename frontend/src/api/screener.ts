export async function getScreener() {
  const res = await fetch("http://localhost:8000/screener");
  return res.json();
}

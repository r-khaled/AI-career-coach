// Minimal same-origin helpers; UI presentation and draft state remain React-owned.
export async function guided(path, {method = 'GET', body} = {}) {
  const response = await fetch(`/api/v2${path}`, {
    method, credentials: 'same-origin', headers: {'Content-Type': 'application/json'},
    ...(body === undefined ? {} : {body: JSON.stringify(body)})
  });
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error(data.error?.message || 'Request failed'), {status: response.status, data});
  return {status: response.status, data};
}

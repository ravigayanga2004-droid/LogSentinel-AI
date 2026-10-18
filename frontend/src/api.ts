export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export function csrf() {
  return (
    document.cookie
      .split('; ')
      .find((row) => row.startsWith('ls_csrf='))
      ?.split('=')
      .slice(1)
      .join('=') ?? ''
  );
}
export function workspaceId() {
  return localStorage.getItem('ls_workspace') ?? '';
}
export function headers() {
  return { 'x-csrf-token': csrf(), 'x-workspace-id': workspaceId() };
}
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    headers: {
      ...headers(),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((item: { field: string; message: string }) => `${item.field}: ${item.message}`)
              .join('; ')
          : (detail?.message ?? 'Request failed. Please try again.');
    throw new ApiError(response.status, message);
  }
  return data as T;
}
export function params(values: Record<string, unknown>) {
  return new URLSearchParams(
    Object.entries(values)
      .filter(
        ([, value]) => value !== '' && value !== null && value !== undefined && value !== false,
      )
      .map(([key, value]) => [key, String(value)]),
  ).toString();
}
export function upload(
  sourceId: string,
  body: FormData,
  onProgress: (value: number) => void,
): Promise<import('./types').Job> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `/api/sources/${sourceId}/upload`);
    Object.entries(headers()).forEach(([name, value]) => xhr.setRequestHeader(name, value));
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100));
    };
    xhr.onerror = () => reject(new Error('Upload connection failed. Please retry.'));
    xhr.onload = () => {
      const data = JSON.parse(xhr.responseText || '{}');
      if (xhr.status < 300) resolve(data);
      else
        reject(
          new Error(
            typeof data.detail === 'string'
              ? data.detail
              : (data.detail?.message ??
                  'Import validation failed. Check the file, format and column mappings.'),
          ),
        );
    };
    xhr.send(body);
  });
}

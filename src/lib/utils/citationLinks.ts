// Rome corpus citations open through RomeGI's sign-on-click endpoint, which signs a
// fresh GCS URL when the user clicks. Old chats stored GCS signed URLs that expire;
// those are routed through the same endpoint so they keep working.
export const ROME_PDF_PATH = '/api/v1/rome/pdf';

const GCS_HOSTS = ['storage.googleapis.com', 'storage.cloud.google.com'];
const GCS_VIRTUAL_HOST_SUFFIX = '.storage.googleapis.com';

const isGcsUrl = (url: string): boolean => {
	try {
		const { protocol, hostname } = new URL(url);
		return (
			protocol === 'https:' &&
			(GCS_HOSTS.includes(hostname) || hostname.endsWith(GCS_VIRTUAL_HOST_SUFFIX))
		);
	} catch {
		return false;
	}
};

export const isCorpusCitationUrl = (url: string | null | undefined): boolean =>
	!!url && (url.startsWith(`${ROME_PDF_PATH}?`) || isGcsUrl(url));

export const resolveCitationHref = (
	url: string | null | undefined,
	page: unknown,
	baseUrl: string
): string | null => {
	if (!url) return null;
	if (url.startsWith(`${ROME_PDF_PATH}?`)) return `${baseUrl}${url}`;
	if (isGcsUrl(url)) {
		const pageParam = /^\d+$/.test(String(page ?? '')) ? `&page=${page}` : '';
		return `${baseUrl}${ROME_PDF_PATH}?src=${encodeURIComponent(url)}${pageParam}`;
	}
	return url.includes('http') ? url : null;
};

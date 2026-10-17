import { describe, expect, it } from 'vitest';
import { isCorpusCitationUrl, resolveCitationHref } from './citationLinks';

const B = 'https://romegi.example';
const LEGACY = 'https://storage.googleapis.com/c/raw/x.pdf?X-Goog-Signature=a';
const CONSOLE = 'https://storage.cloud.google.com/c/raw/x.pdf';

describe('resolveCitationHref', () => {
	it('prefixes stable links', () =>
		expect(resolveCitationHref('/api/v1/rome/pdf?path=raw%2Fx.pdf&page=2', '2', B)).toBe(
			`${B}/api/v1/rome/pdf?path=raw%2Fx.pdf&page=2`
		));
	it('works with an empty base url (production, same origin)', () =>
		expect(resolveCitationHref('/api/v1/rome/pdf?path=raw%2Fx.pdf', null, '')).toBe(
			'/api/v1/rome/pdf?path=raw%2Fx.pdf'
		));
	it('rewrites legacy signed links with page, dropping the old signature', () =>
		expect(resolveCitationHref(LEGACY, '7', B)).toBe(
			`${B}/api/v1/rome/pdf?src=${encodeURIComponent('https://storage.googleapis.com/c/raw/x.pdf')}&page=7`
		));
	it('keeps the percent-encoded object key when dropping the query', () =>
		expect(
			resolveCitationHref(
				'https://storage.googleapis.com/c/raw/A%20B%20(1).pdf?X-Goog-Signature=a',
				null,
				B
			)
		).toBe(
			`${B}/api/v1/rome/pdf?src=${encodeURIComponent('https://storage.googleapis.com/c/raw/A%20B%20(1).pdf')}`
		));
	it('rewrites console links without a non-numeric page', () =>
		expect(resolveCitationHref(CONSOLE, 'N/A', B)).toBe(
			`${B}/api/v1/rome/pdf?src=${encodeURIComponent(CONSOLE)}`
		));
	it('leaves web links alone', () =>
		expect(resolveCitationHref('https://pubmed.ncbi.nlm.nih.gov/1/', 1, B)).toBe(
			'https://pubmed.ncbi.nlm.nih.gov/1/'
		));
	it('returns null for empty', () => expect(resolveCitationHref(undefined, null, B)).toBeNull());
	it('returns null for non-http, non-corpus strings', () =>
		expect(resolveCitationHref('doc.pdf', null, B)).toBeNull());
});

describe('isCorpusCitationUrl', () => {
	it('accepts stable links', () =>
		expect(isCorpusCitationUrl('/api/v1/rome/pdf?path=x')).toBe(true));
	it('accepts path-style GCS links', () => expect(isCorpusCitationUrl(LEGACY)).toBe(true));
	it('accepts virtual-host GCS links', () =>
		expect(isCorpusCitationUrl('https://c.storage.googleapis.com/raw/x.pdf?a=1')).toBe(true));
	it('accepts console links', () => expect(isCorpusCitationUrl(CONSOLE)).toBe(true));
	it('ignores look-alike hosts', () =>
		expect(isCorpusCitationUrl('https://storage.googleapis.com.evil.com/x.pdf')).toBe(false));
	it('ignores http GCS links', () =>
		expect(isCorpusCitationUrl('http://storage.googleapis.com/c/raw/x.pdf')).toBe(false));
	it('ignores web links', () =>
		expect(isCorpusCitationUrl('https://example.com/a.pdf')).toBe(false));
	it('ignores empty', () => expect(isCorpusCitationUrl(undefined)).toBe(false));
});

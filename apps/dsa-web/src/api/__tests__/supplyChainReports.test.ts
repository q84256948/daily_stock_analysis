import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { supplyChainReportApi } from '../supplyChainReports';

const { get, del } = vi.hoisted(() => ({
  get: vi.fn(),
  del: vi.fn(),
}));

// mock axios apiClient（getReports / getReport / deleteReport 走 axios）
vi.mock('../index', () => ({
  default: { get, delete: del },
}));

// mock 全局 fetch（generateStream / downloadPdf 走原生 fetch）
const fetchMock = vi.fn();
vi.stubGlobal('fetch', fetchMock);

describe('supplyChainReportApi', () => {
  beforeEach(() => {
    get.mockReset();
    del.mockReset();
    fetchMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('getReports 解包 data 数组并带分页参数', async () => {
    get.mockResolvedValueOnce({
      data: {
        success: true,
        data: [
          {
            id: 'sc_202606271530_1',
            topic: '光模块产业链',
            research_hint: 'CPO 上游',
            status: 'success',
            has_pdf: true,
          },
        ],
        total: 1,
      },
    });

    const result = await supplyChainReportApi.getReports(50, 0);

    expect(get).toHaveBeenCalledWith('/api/v1/supply-chain/reports', {
      params: { limit: 50, offset: 0 },
    });
    expect(result).toHaveLength(1);
    expect(result[0].topic).toBe('光模块产业链');
    expect(result[0].research_hint).toBe('CPO 上游');
    expect(result[0].has_pdf).toBe(true);
  });

  it('getReport 解包详情', async () => {
    get.mockResolvedValueOnce({
      data: {
        success: true,
        data: {
          id: 'sc_202606271530_1',
          topic: '光模块产业链',
          markdown: '# 供应链分析报告',
          status: 'success',
          provider: 'test',
        },
      },
    });

    const detail = await supplyChainReportApi.getReport('sc_202606271530_1');

    expect(get).toHaveBeenCalledWith('/api/v1/supply-chain/reports/sc_202606271530_1');
    expect(detail.markdown).toBe('# 供应链分析报告');
    expect(detail.topic).toBe('光模块产业链');
  });

  it('deleteReport 调用 delete 端点', async () => {
    del.mockResolvedValueOnce({ data: { success: true } });
    await supplyChainReportApi.deleteReport('sc_202606271530_1');
    expect(del).toHaveBeenCalledWith('/api/v1/supply-chain/reports/sc_202606271530_1');
  });

  it('generateStream 成功返回原始 Response（带 topic/research_hint）', async () => {
    const fakeResponse = { ok: true, body: { getReader: () => {} } };
    fetchMock.mockResolvedValueOnce(fakeResponse);

    const response = await supplyChainReportApi.generateStream({
      topic: '光模块产业链',
      research_hint: 'CPO 上游',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/supply-chain/generate/stream'),
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ topic: '光模块产业链', research_hint: 'CPO 上游' }),
      }),
    );
    expect(response).toBe(fakeResponse);
  });

  it('generateStream 非 2xx 抛错（走 error 解析分支）', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 422,
      statusText: 'Unprocessable Entity',
      headers: { get: () => 'application/json' },
      json: async () => ({ detail: 'topic required' }),
    });

    await expect(
      supplyChainReportApi.generateStream({ topic: '' }),
    ).rejects.toThrow();
  });

  it('downloadPdf 成功时走 blob 下载路径并带正确文件名', async () => {
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    fetchMock.mockResolvedValueOnce({
      ok: true,
      blob: async () => new Blob(['pdf'], { type: 'application/pdf' }),
    });

    await supplyChainReportApi.downloadPdf('sc_202606271530_1');

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/supply-chain/reports/sc_202606271530_1/pdf'),
      { credentials: 'include' },
    );
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:x');
  });

  it('downloadPdf 失败抛带状态码的错误', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'PDF 文件不存在' }),
    });

    await expect(
      supplyChainReportApi.downloadPdf('sc_202606271530_1'),
    ).rejects.toThrow('404');
  });
});

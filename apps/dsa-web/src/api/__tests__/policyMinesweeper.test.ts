import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { policyMinesweeperApi } from '../policyMinesweeper';

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

describe('policyMinesweeperApi', () => {
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
            id: '600519_202606261200',
            stock_code: '600519',
            stock_name: '贵州茅台',
            status: 'success',
            composite_score: -35,
            verdict: '中等利空',
            confidence: 78,
            has_pdf: true,
          },
        ],
        total: 1,
      },
    });

    const result = await policyMinesweeperApi.getReports(50, 0);

    expect(get).toHaveBeenCalledWith('/api/v1/policy-minesweeper/reports', {
      params: { limit: 50, offset: 0 },
    });
    expect(result).toHaveLength(1);
    expect(result[0].composite_score).toBe(-35);
    expect(result[0].verdict).toBe('中等利空');
  });

  it('getReport 解包详情', async () => {
    get.mockResolvedValueOnce({
      data: {
        success: true,
        data: {
          id: '600519_202606261200',
          stock_code: '600519',
          markdown: '# 排雷报告',
          alpha_ok: true,
          beta_ok: true,
          omega_ok: true,
        },
      },
    });

    const detail = await policyMinesweeperApi.getReport('600519_202606261200');

    expect(get).toHaveBeenCalledWith('/api/v1/policy-minesweeper/reports/600519_202606261200');
    expect(detail.markdown).toBe('# 排雷报告');
    expect(detail.alpha_ok).toBe(true);
  });

  it('deleteReport 调用 delete 端点', async () => {
    del.mockResolvedValueOnce({ data: { success: true } });
    await policyMinesweeperApi.deleteReport('600519_202606261200');
    expect(del).toHaveBeenCalledWith('/api/v1/policy-minesweeper/reports/600519_202606261200');
  });

  it('generateStream 成功返回原始 Response', async () => {
    const fakeResponse = { ok: true, body: { getReader: () => {} } };
    fetchMock.mockResolvedValueOnce(fakeResponse);

    const response = await policyMinesweeperApi.generateStream({
      stock_code: '600519',
      stock_name: '贵州茅台',
      horizon: 'long',
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/policy-minesweeper/generate/stream'),
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ stock_code: '600519', stock_name: '贵州茅台', horizon: 'long' }),
      }),
    );
    expect(response).toBe(fakeResponse);
  });

  it('generateStream 非 2xx 抛错（走 error 解析分支）', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: 'Bad Request',
      headers: { get: () => 'text/plain' },
      text: async () => '非 A 股代码',
    });

    await expect(
      policyMinesweeperApi.generateStream({ stock_code: 'AAPL' }),
    ).rejects.toThrow();
  });

  it('downloadPdf 成功时走 blob 下载路径', async () => {
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    // jsdom 真实 <a> 元素：appendChild/click/removeChild 均可正常执行
    fetchMock.mockResolvedValueOnce({
      ok: true,
      blob: async () => new Blob(['pdf'], { type: 'application/pdf' }),
    });

    await policyMinesweeperApi.downloadPdf('600519_202606261200');

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/policy-minesweeper/reports/600519_202606261200/pdf'),
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
      policyMinesweeperApi.downloadPdf('600519_202606261200'),
    ).rejects.toThrow('404');
  });
});

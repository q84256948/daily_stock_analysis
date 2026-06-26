import apiClient from './index';
import { API_BASE_URL } from '../utils/constants';
import { createApiError, isApiRequestError, parseApiError } from './error';

/** 时间窗口：short(1-5日) / medium(1-4周) / long(1-6月)。 */
export type PolicyMinesweeperHorizon = 'short' | 'medium' | 'long';

export interface PolicyMinesweeperGenerateRequest {
  stock_code: string;
  stock_name?: string;
  horizon?: PolicyMinesweeperHorizon;
}

export interface PolicyMinesweeperStreamOptions {
  signal?: AbortSignal;
}

export interface PolicyMinesweeperReportItem {
  id: string;
  stock_code: string;
  stock_name?: string;
  created_at?: string;
  status?: string;
  horizon?: string;
  alpha_ok?: boolean;
  beta_ok?: boolean;
  omega_ok?: boolean;
  /** 综合分 -100(强利空) ~ +100(强利好)。best-effort 解析，可能为 null。 */
  composite_score?: number | null;
  /** 中文等级（如『中等利空』），可能为 null。 */
  verdict?: string | null;
  /** 置信度 0~100，可能为 null。 */
  confidence?: number | null;
  has_pdf?: boolean;
}

export interface PolicyMinesweeperReportDetail extends PolicyMinesweeperReportItem {
  markdown: string;
  md_path?: string;
  total_steps?: number;
  total_tokens?: number;
  provider?: string;
  error?: string;
}

/**
 * 政策与公告双维度排雷 API 客户端。
 *
 * 路径前缀 `/api/v1/policy-minesweeper/...`（继承全局 AuthMiddleware）。
 * 与深度投研同构：generate 是 SSE 流式一次性生成（α/β 并行 → Ω 综合），
 * reports 是历史报告 CRUD（元数据在 SQLite，正文/PDF 在文件）。
 */
export const policyMinesweeperApi = {
  async getReports(limit = 50, offset = 0): Promise<PolicyMinesweeperReportItem[]> {
    const response = await apiClient.get<{
      success: boolean;
      data: PolicyMinesweeperReportItem[];
      total: number;
    }>('/api/v1/policy-minesweeper/reports', { params: { limit, offset } });
    return response.data.data;
  },

  async getReport(reportId: string): Promise<PolicyMinesweeperReportDetail> {
    const response = await apiClient.get<{
      success: boolean;
      data: PolicyMinesweeperReportDetail;
    }>(`/api/v1/policy-minesweeper/reports/${reportId}`);
    return response.data.data;
  },

  async deleteReport(reportId: string): Promise<void> {
    await apiClient.delete(`/api/v1/policy-minesweeper/reports/${reportId}`);
  },

  /**
   * SSE 流式生成排雷报告（α 公告 + β 政策 并行 → Ω 综合裁决）。
   * 返回原始 Response，由 usePolicyMinesweeper hook 解析 `data: ` 事件流。
   * 事件类型：thinking / tool_start / tool_done / generating / done / error / heartbeat。
   */
  async generateStream(
    payload: PolicyMinesweeperGenerateRequest,
    options?: PolicyMinesweeperStreamOptions,
  ): Promise<Response> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/policy-minesweeper/generate/stream`;
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        credentials: 'include',
        signal: options?.signal,
      });

      if (response.ok) {
        return response;
      }

      const contentType = response.headers.get('content-type') || '';
      let responseData: unknown = null;
      if (contentType.includes('application/json')) {
        responseData = await response.json().catch(() => null);
      } else {
        responseData = await response.text().catch(() => null);
      }

      const parsed = parseApiError({
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
      throw createApiError(parsed, {
        response: {
          status: response.status,
          statusText: response.statusText,
          data: responseData,
        },
      });
    } catch (error: unknown) {
      if (isApiRequestError(error)) {
        throw error;
      }
      if (error instanceof Error && error.name === 'AbortError') {
        throw error;
      }

      const parsed = parseApiError(error);
      throw createApiError(parsed, { cause: error });
    }
  },

  /**
   * 下载报告 PDF（惰性生成：首次请求触发后端 WeasyPrint 渲染）。
   * 用 fetch blob + <a download> 触发浏览器下载（带认证 cookie，不被弹窗拦截）。
   */
  async downloadPdf(reportId: string): Promise<void> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/policy-minesweeper/reports/${reportId}/pdf`;
    const response = await fetch(url, { credentials: 'include' });
    if (!response.ok) {
      let backendDetail = '';
      try {
        const body = await response.json();
        const msg = body?.message || body?.detail;
        backendDetail = msg ? `: ${msg}` : '';
      } catch {
        // 非 JSON 响应，忽略
      }
      throw new Error(
        `PDF 下载失败（${response.status}）${backendDetail}，请检查日志或稍后重试`,
      );
    }
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `policy_minesweeper_${reportId}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  },
};

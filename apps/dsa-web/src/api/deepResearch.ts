import apiClient from './index';
import { API_BASE_URL } from '../utils/constants';
import { createApiError, isApiRequestError, parseApiError } from './error';

export interface DeepResearchGenerateRequest {
  stock_code: string;
  stock_name?: string;
  report_type?: string;
}

export interface DeepResearchStreamOptions {
  signal?: AbortSignal;
}

export interface DeepResearchReportItem {
  id: string;
  stock_code: string;
  stock_name?: string;
  created_at?: string;
  status?: string;
  quality_score?: number;
  missing_layers?: string[];
  has_pdf?: boolean;
}

export interface DeepResearchReportDetail extends DeepResearchReportItem {
  markdown: string;
  md_path?: string;
  total_steps?: number;
  total_tokens?: number;
  provider?: string;
  error?: string;
}

/**
 * A股深度投研报告 API 客户端。
 *
 * 路径前缀 `/api/v1/deep-research/...`（继承全局 AuthMiddleware）。
 * 与 chat 类 API 的差异：generate 是 SSE 流式一次性生成（非多轮对话），
 * reports 是历史报告 CRUD（元数据在 SQLite，正文/PDF 在文件）。
 */
export const deepResearchApi = {
  async getReports(limit = 50, offset = 0): Promise<DeepResearchReportItem[]> {
    const response = await apiClient.get<{
      success: boolean;
      data: DeepResearchReportItem[];
      total: number;
    }>('/api/v1/deep-research/reports', { params: { limit, offset } });
    return response.data.data;
  },

  async getReport(reportId: string): Promise<DeepResearchReportDetail> {
    const response = await apiClient.get<{
      success: boolean;
      data: DeepResearchReportDetail;
    }>(`/api/v1/deep-research/reports/${reportId}`);
    return response.data.data;
  },

  async deleteReport(reportId: string): Promise<void> {
    await apiClient.delete(`/api/v1/deep-research/reports/${reportId}`);
  },

  /**
   * SSE 流式生成深度投研报告。
   * 返回原始 Response，由 useDeepResearch hook 解析 `data: ` 事件流。
   * 事件类型：thinking / tool_start / tool_done / generating / done / error / heartbeat。
   */
  async generateStream(
    payload: DeepResearchGenerateRequest,
    options?: DeepResearchStreamOptions,
  ): Promise<Response> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/deep-research/generate/stream`;
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
   * 下载报告 PDF（惰性生成：首次请求触发后端 xhtml2pdf 渲染）。
   * 用 fetch blob + <a download> 触发浏览器下载（带认证 cookie，不被弹窗拦截）。
   */
  async downloadPdf(reportId: string): Promise<void> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/deep-research/reports/${reportId}/pdf`;
    const response = await fetch(url, { credentials: 'include' });
    if (!response.ok) {
      // 后端失败返回 {error, message, detail}（全局异常包装）；解析回显更具体原因
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
    a.download = `deep_research_${reportId}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  },
};

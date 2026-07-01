import apiClient from './index';
import { API_BASE_URL } from '../utils/constants';
import { createApiError, isApiRequestError, parseApiError } from './error';
import { downloadPdfFromUrl } from './download';

export interface SupplyChainGenerateRequest {
  topic: string;
  research_hint?: string;
  // 可选单股绑定（按 docs/pdf-download-filename-plan.md §供应链报告边界 阶段 1）：
  // 两者至少给一个时，PDF 文件名遵循单股型命名；都为空时走主题型（向后兼容）。
  stock_code?: string;
  stock_name?: string;
}

export interface SupplyChainStreamOptions {
  signal?: AbortSignal;
}

export interface SupplyChainReportItem {
  id: string;
  topic: string;
  research_hint?: string;
  stock_code?: string;
  stock_name?: string;
  created_at?: string;
  status?: string;
  has_pdf?: boolean;
}

export interface SupplyChainReportDetail extends SupplyChainReportItem {
  markdown: string;
  md_path?: string;
  total_steps?: number;
  total_tokens?: number;
  provider?: string;
  model?: string;
  error?: string;
}

/**
 * 供应链分析表单式报告 API 客户端。
 *
 * 路径前缀 `/api/v1/supply-chain/...`（继承全局 AuthMiddleware，与旧 chat 端点同前缀、路径不冲突）。
 * 与 chat 类 API 的差异：generate 是 SSE 流式一次性生成（非多轮对话），
 * reports 是历史报告 CRUD（元数据在 SQLite，正文/PDF 在文件）。
 */
export const supplyChainReportApi = {
  async getReports(limit = 50, offset = 0): Promise<SupplyChainReportItem[]> {
    const response = await apiClient.get<{
      success: boolean;
      data: SupplyChainReportItem[];
      total: number;
    }>('/api/v1/supply-chain/reports', { params: { limit, offset } });
    return response.data.data;
  },

  async getReport(reportId: string): Promise<SupplyChainReportDetail> {
    const response = await apiClient.get<{
      success: boolean;
      data: SupplyChainReportDetail;
    }>(`/api/v1/supply-chain/reports/${reportId}`);
    return response.data.data;
  },

  async deleteReport(reportId: string): Promise<void> {
    await apiClient.delete(`/api/v1/supply-chain/reports/${reportId}`);
  },

  /**
   * SSE 流式生成供应链报告。
   * 返回原始 Response，由 useSupplyChainReport hook 解析 `data: ` 事件流。
   * 事件类型：thinking / tool_start / tool_done / generating / done / error / heartbeat。
   */
  async generateStream(
    payload: SupplyChainGenerateRequest,
    options?: SupplyChainStreamOptions,
  ): Promise<Response> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/supply-chain/generate/stream`;
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
   * 下载报告 PDF（惰性生成：首次请求触发后端渲染）。
   * 用 fetch blob + <a download> 触发浏览器下载（带认证 cookie，不被弹窗拦截）。
   * 业务文件名从后端 Content-Disposition 解析（按 docs/pdf-download-filename-plan.md）；
   * 单股绑定走 ``股票名（代码）供应链分析报告YYYYMMDD.pdf``，未绑定走主题型兜底。
   */
  async downloadPdf(reportId: string): Promise<void> {
    const base = API_BASE_URL || '';
    const url = `${base}/api/v1/supply-chain/reports/${reportId}/pdf`;
    await downloadPdfFromUrl(url, 'supply_chain', reportId);
  },
};

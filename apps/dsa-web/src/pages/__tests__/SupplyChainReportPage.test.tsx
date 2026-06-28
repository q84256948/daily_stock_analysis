import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  getReports: vi.fn(),
  getReport: vi.fn(),
  deleteReport: vi.fn(),
  downloadPdf: vi.fn(),
  generateStream: vi.fn(),
}));

vi.mock('../../api/supplyChainReports', () => ({
  supplyChainReportApi: api,
}));

import SupplyChainReportPage from '../SupplyChainReportPage';

const encoder = new TextEncoder();

function createStreamResponse(lines: string[]): Response {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(lines.map((l) => l + '\n\n').join('')));
        controller.close();
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  );
}

function data(line: object): string {
  return `data: ${JSON.stringify(line)}`;
}

function doneStream(markdown = '# 供应链分析报告', reportId = 'sc_202606271530_1'): Response {
  return createStreamResponse([
    data({ type: 'done', success: true, report_id: reportId, status: 'success', markdown }),
  ]);
}

const topicInput = () => screen.getByPlaceholderText(/分析主题/);
const hintInput = () => screen.getByPlaceholderText(/增加供应链线索/);
const generateBtn = () => screen.getByRole('button', { name: '生成报告' });

describe('SupplyChainReportPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.alert = vi.fn();
    api.getReports.mockResolvedValue([]);
    api.getReport.mockResolvedValue({ id: 'sc_202606271530_1', topic: '光模块产业链', markdown: '# 历史', status: 'success' });
    api.deleteReport.mockResolvedValue(undefined);
    api.downloadPdf.mockResolvedValue(undefined);
    api.generateStream.mockResolvedValue(doneStream());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('挂载时加载历史列表', async () => {
    api.getReports.mockResolvedValue([{ id: 'sc_1', topic: '历史主题', status: 'success' }]);
    render(<SupplyChainReportPage />);
    await waitFor(() => expect(api.getReports).toHaveBeenCalled());
    expect(await screen.findByText('历史主题')).toBeInTheDocument();
  });

  it('主题为空点击生成 → 提示且不调 generateStream', async () => {
    render(<SupplyChainReportPage />);
    fireEvent.click(generateBtn());
    await waitFor(() => expect(screen.getByText('请输入分析主题')).toBeInTheDocument());
    expect(api.generateStream).not.toHaveBeenCalled();
  });

  it('快捷模板填充主题', async () => {
    render(<SupplyChainReportPage />);
    fireEvent.click(await screen.findByText('A 股 AI 半导体供应链'));
    expect((topicInput() as HTMLTextAreaElement).value).toBe('A 股 AI 半导体供应链');
  });

  it('带线索生成 → generateStream 收到 research_hint，发送后清空线索、保留主题', async () => {
    render(<SupplyChainReportPage />);
    fireEvent.change(topicInput(), { target: { value: '光模块产业链' } });
    fireEvent.change(hintInput(), { target: { value: 'CPO 上游薄膜铌酸锂' } });
    fireEvent.click(generateBtn());

    await waitFor(() =>
      expect(api.generateStream).toHaveBeenCalledWith(
        { topic: '光模块产业链', research_hint: 'CPO 上游薄膜铌酸锂' },
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      ),
    );
    // 报告渲染后才出现「复制 Markdown」按钮（showReport=true 的可靠信号）
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /复制 Markdown/ })).toBeInTheDocument(),
    );
    expect((topicInput() as HTMLTextAreaElement).value).toBe('光模块产业链');
    expect((hintInput() as HTMLTextAreaElement).value).toBe('');
  });

  it('无线索生成 → 不传 research_hint', async () => {
    render(<SupplyChainReportPage />);
    fireEvent.change(topicInput(), { target: { value: '光模块产业链' } });
    fireEvent.click(generateBtn());
    await waitFor(() =>
      expect(api.generateStream).toHaveBeenCalledWith(
        { topic: '光模块产业链', research_hint: undefined },
        expect.any(Object),
      ),
    );
  });

  it('SSE error → 展示错误', async () => {
    api.generateStream.mockResolvedValueOnce(
      createStreamResponse([data({ type: 'error', message: '后端错误' })]),
    );
    render(<SupplyChainReportPage />);
    fireEvent.change(topicInput(), { target: { value: '主题' } });
    fireEvent.click(generateBtn());
    await waitFor(() => expect(screen.getByText('后端错误')).toBeInTheDocument());
  });

  it('报告生成后 → 下载 PDF 按钮调用 downloadPdf', async () => {
    render(<SupplyChainReportPage />);
    fireEvent.change(topicInput(), { target: { value: '光模块产业链' } });
    fireEvent.click(generateBtn());
    const pdfBtn = await screen.findByRole('button', { name: /下载 PDF/ });
    fireEvent.click(pdfBtn);
    await waitFor(() => expect(api.downloadPdf).toHaveBeenCalledWith('sc_202606271530_1'));
  });

  it('报告生成后 → 复制 Markdown 调用 clipboard', async () => {
    const writeText = vi.fn();
    Object.assign(navigator, { clipboard: { writeText } });
    render(<SupplyChainReportPage />);
    fireEvent.change(topicInput(), { target: { value: '光模块产业链' } });
    fireEvent.click(generateBtn());
    const copyBtn = await screen.findByRole('button', { name: /复制 Markdown/ });
    fireEvent.click(copyBtn);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith('# 供应链分析报告'));
  });

  it('选中历史报告 → 调 getReport 且不回填线索', async () => {
    api.getReports.mockResolvedValue([{ id: 'sc_1', topic: '历史主题', status: 'success' }]);
    render(<SupplyChainReportPage />);
    fireEvent.change(hintInput(), { target: { value: '当前线索' } });
    fireEvent.click(await screen.findByText('历史主题'));
    await waitFor(() => expect(api.getReport).toHaveBeenCalledWith('sc_1'));
    // 历史报告不含 researchHint 回填：线索输入框仍为用户当前输入（未被动）
    expect((hintInput() as HTMLTextAreaElement).value).toBe('当前线索');
  });

  it('删除历史报告 → 调 deleteReport', async () => {
    api.getReports.mockResolvedValue([{ id: 'sc_1', topic: '历史主题', status: 'success' }]);
    render(<SupplyChainReportPage />);
    await screen.findByText('历史主题');
    const deleteIcon = screen.getByRole('button', { name: '删除' });
    fireEvent.click(deleteIcon);
    await waitFor(() => expect(api.deleteReport).toHaveBeenCalledWith('sc_1'));
  });
});

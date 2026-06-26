import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { PolicyMinesweeperPage } from '../PolicyMinesweeperPage';

const { getReports } = vi.hoisted(() => ({ getReports: vi.fn() }));

vi.mock('../../api/policyMinesweeper', () => ({
  policyMinesweeperApi: { getReports },
}));

// 隔离重型子组件：本测试只验证页面装配/交互，不验证联想/Markdown 渲染内部
vi.mock('../../components/StockAutocomplete/StockAutocomplete', () => ({
  StockAutocomplete: (props: { placeholder?: string; disabled?: boolean }) => (
    <input data-testid="stock-input" placeholder={props.placeholder} disabled={props.disabled} />
  ),
}));
vi.mock('../../components/report/ReportMarkdownBody', () => ({
  ReportMarkdownBody: ({ content }: { content: string }) => <div>{content}</div>,
}));

describe('PolicyMinesweeperPage', () => {
  beforeEach(() => {
    getReports.mockReset();
    getReports.mockResolvedValue([]);
  });

  it('渲染标题 + 空状态提示 + 开始排雷按钮，并加载历史', async () => {
    render(<PolicyMinesweeperPage />);

    expect(screen.getByText('政策与公告双维度排雷')).toBeInTheDocument();
    expect(screen.getByText(/三角色并行/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /开始排雷/ })).toBeInTheDocument();

    await waitFor(() => expect(getReports).toHaveBeenCalledWith(50));
  });

  it('未选股票点开始排雷 → 提示请先选择', async () => {
    render(<PolicyMinesweeperPage />);

    fireEvent.click(screen.getByRole('button', { name: /开始排雷/ }));

    expect(await screen.findByText('请先选择一只 A 股')).toBeInTheDocument();
  });

  it('时间窗口默认中期，点击长期后高亮切换', async () => {
    render(<PolicyMinesweeperPage />);

    const longBtn = screen.getByRole('button', { name: '长期' });
    const mediumBtn = screen.getByRole('button', { name: '中期' });
    // 默认中期高亮、长期不高亮
    expect(mediumBtn.className).toContain('bg-cyan');
    expect(longBtn.className).not.toContain('bg-cyan');

    fireEvent.click(longBtn);

    // 切换后长期高亮、中期取消
    expect(longBtn.className).toContain('bg-cyan');
    expect(mediumBtn.className).not.toContain('bg-cyan');
  });
});

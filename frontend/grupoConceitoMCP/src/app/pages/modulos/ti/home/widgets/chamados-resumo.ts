import { FatiaRosca } from '../../../../../componentes/grafico-rosca/grafico-rosca';
import { MCP_API_BASE_URL } from '../../../../../app-config';

export const URL_CHAMADOS = `${MCP_API_BASE_URL}/api/ti/chamados`;

export interface ChamadoResumo {
  status: string;
}

const ROTULOS_STATUS: Record<string, string> = {
  novo: 'Novo',
  aguardando_usuario: 'Aguardando usuário',
  fila_atendimento: 'Fila de atendimento',
};

const CORES_STATUS: Record<string, string> = {
  novo: '#e8871e',
  aguardando_usuario: '#b5620a',
  fila_atendimento: '#2f9e58',
};

/** Widgets de chamados (total + por-status) fazem cada um seu próprio GET
 * — 1 request a mais é barato e mantém cada widget independente; o que
 * vale a pena não duplicar é esta tabela de rótulo/cor. */
export function contarPorStatus(chamados: ChamadoResumo[]): FatiaRosca[] {
  const porStatus = new Map<string, number>();
  for (const chamado of chamados) {
    porStatus.set(chamado.status, (porStatus.get(chamado.status) ?? 0) + 1);
  }
  return Array.from(porStatus.entries()).map(([status, quantidade]) => ({
    nome: ROTULOS_STATUS[status] ?? status,
    valor: quantidade,
    cor: CORES_STATUS[status] ?? '#5b6b62',
  }));
}

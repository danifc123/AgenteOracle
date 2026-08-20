import {
  NivelSenioridade,
  ROTULOS_SENIORIDADE,
  ROTULOS_STATUS_FORMACAO,
  StatusFormacao,
} from './analise-curriculo';

export function rotuloSenioridade(nivel: NivelSenioridade | undefined): string {
  return ROTULOS_SENIORIDADE[nivel ?? 'nao_identificado'];
}

export function rotuloStatusFormacao(status: StatusFormacao): string {
  return ROTULOS_STATUS_FORMACAO[status];
}

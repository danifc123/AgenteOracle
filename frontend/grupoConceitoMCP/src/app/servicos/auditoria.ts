import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../app-config';

export interface AchadoAuditoria {
  modulo: string;
  view: string;
  campo: string;
  valor: string;
  descricao: string;
}

/** Estado da auditoria de dados, compartilhado entre o sino do layout, o
 * botão do sidebar e o painel que mostra o resultado — extraído pra serviço
 * porque nenhum desses três é dono exclusivo do estado (mesmo caso de uso que
 * já levou `servicos/previsao-stream.ts` a existir). Nada aqui roda sozinho:
 * `abrir()` só mostra o painel (não busca nada — reabrir o painel pra olhar o
 * que já foi encontrado não pode disparar outra chamada ao Ollama sozinho);
 * só `buscar()`, chamado por um botão dedicado DENTRO do painel, dispara a
 * análise de verdade.
 *
 * Escopada por módulo/departamento, de propósito: cada departamento roda e
 * revisa só a própria auditoria, nunca a de outro — reflete a mesma regra do
 * backend (`GET /api/auditoria?modulo=`). Qual módulo é decidido DENTRO do
 * painel, via `selecionarModulo` (`auditoria-painel` mostra um seletor só
 * quando o usuário tem mais de uma opção liberada — hoje sempre 1, então na
 * prática se auto-seleciona sem o usuário precisar escolher nada). */
@Injectable({ providedIn: 'root' })
export class Auditoria {
  private readonly http = inject(HttpClient);

  readonly aberto = signal(false);
  readonly moduloAtual = signal<string | null>(null);
  readonly achados = signal<AchadoAuditoria[]>([]);
  readonly carregando = signal(false);
  readonly erro = signal<string | null>(null);
  /** Diferencia "nunca rodou" de "rodou e não achou nada" — o painel mostra
   * um estado neutro (com o botão de rodar) até a primeira busca terminar. */
  readonly jaExecutou = signal(false);
  /** Incrementa a cada execução concluída com sucesso OU achado dispensado —
   * outras telas (ex: a Lista de Auditoria) observam esse signal pra saber
   * quando re-buscar o próprio histórico, sem precisar que o usuário
   * recarregue a página. */
  readonly mudancas = signal(0);

  abrir(): void {
    this.aberto.set(true);
  }

  buscar(): void {
    const modulo = this.moduloAtual();
    if (!modulo) {
      return;
    }

    this.carregando.set(true);
    this.erro.set(null);

    this.http
      .get<AchadoAuditoria[]>(`${MCP_API_BASE_URL}/api/auditoria`, { params: { modulo } })
      .subscribe({
        next: (achados) => {
          this.achados.set(achados);
          this.carregando.set(false);
          this.jaExecutou.set(true);
          this.mudancas.update((atual) => atual + 1);
        },
        error: () => {
          this.erro.set(
            'Não foi possível rodar a auditoria. Verifique se o servidor e o Ollama estão em execução.',
          );
          this.carregando.set(false);
          this.jaExecutou.set(true);
        },
      });
  }

  dispensar(achado: AchadoAuditoria): void {
    this.http.post(`${MCP_API_BASE_URL}/api/auditoria/dispensar`, achado).subscribe({
      next: () => {
        this.achados.update((atual) => atual.filter((item) => item !== achado));
        this.mudancas.update((atual) => atual + 1);
      },
    });
  }

  fechar(): void {
    this.aberto.set(false);
  }

  /** Volta pro estado "nenhum módulo escolhido" — usado pelo seletor quando
   * o usuário tem mais de uma opção e quer trocar de departamento sem
   * fechar o painel. */
  limparSelecao(): void {
    this.moduloAtual.set(null);
    this.achados.set([]);
    this.jaExecutou.set(false);
    this.erro.set(null);
  }

  selecionarModulo(modulo: string): void {
    if (this.moduloAtual() === modulo) {
      return;
    }
    // Troca de departamento não pode mostrar achado de auditoria antiga de
    // outro módulo enquanto a nova busca não roda.
    this.achados.set([]);
    this.jaExecutou.set(false);
    this.erro.set(null);
    this.moduloAtual.set(modulo);
  }
}

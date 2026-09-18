import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';

export interface AchadoAuditoria {
  modulo: string;
  view: string;
  campo: string;
  valor: string;
  descricao: string;
}

export interface AcaoAuditoria {
  id: string;
  rotulo: string;
  descricao: string;
  tipo: 'ia' | 'deterministico';
}

/** Estado da auditoria de dados, compartilhado entre o sino do layout, o
 * botão do sidebar e o painel que mostra o resultado — extraído pra serviço
 * porque nenhum desses três é dono exclusivo do estado (mesmo caso de uso que
 * já levou `servicos/previsao-stream.ts` a existir).
 *
 * Cada módulo tem uma ou mais AÇÕES independentes (`acoesDisponiveis`, ver
 * `GET /api/auditoria/acoes`) — `rodar(acaoId)` roda só UMA, nunca "tudo de
 * uma vez": ação `tipo="ia"` gasta uma consulta real ao Ollama, `tipo=
 * "deterministico"` é só SQL, sem custo de IA. `acaoRodando` guarda qual
 * ação está em voo (só ela mostra spinner no painel, as outras continuam
 * clicáveis... na prática o painel desabilita todas enquanto uma roda, mas
 * o dado já vem certo pra habilitar concorrência no futuro se fizer sentido).
 *
 * `carregarConhecidos()` (chamado no constructor, e de novo a cada troca de
 * módulo) é a ÚNICA coisa automática — lê achado já conhecido via rota
 * barata (`/api/auditoria/historico`, só Postgres, sem IA e sem rodar SQL
 * pesado), pro sino e o painel já virem com o que já se sabe, sem exigir
 * clique nenhum. Escopada por módulo/departamento, de propósito: cada
 * departamento roda e revisa só a própria auditoria, nunca a de outro. */
@Injectable({ providedIn: 'root' })
export class Auditoria {
  private readonly http = inject(HttpClient);

  readonly aberto = signal(false);
  readonly moduloAtual = signal<string | null>(null);
  readonly acoesDisponiveis = signal<AcaoAuditoria[]>([]);
  readonly achados = signal<AchadoAuditoria[]>([]);
  readonly acaoRodando = signal<string | null>(null);
  readonly erro = signal<string | null>(null);
  /** Incrementa a cada execução concluída com sucesso OU achado dispensado —
   * outras telas (ex: a Lista de Auditoria) observam esse signal pra saber
   * quando re-buscar o próprio histórico, sem precisar que o usuário
   * recarregue a página. */
  readonly mudancas = signal(0);

  constructor() {
    this.carregarConhecidos();
  }

  // carregarAcoes/carregarConhecidos só são usadas por selecionarModulo (e
  // carregarConhecidos também pelo constructor) — ficam juntas, antes dela.
  private carregarAcoes(modulo: string): void {
    this.http.get<AcaoAuditoria[]>(`${MCP_API_BASE_URL}/api/auditoria/acoes`, { params: { modulo } }).subscribe({
      next: (acoes) => this.acoesDisponiveis.set(acoes),
      error: () => this.acoesDisponiveis.set([]),
    });
  }

  private carregarConhecidos(modulo?: string): void {
    this.http
      .get<AchadoAuditoria[]>(`${MCP_API_BASE_URL}/api/auditoria/historico`, {
        params: modulo ? { modulo } : {},
      })
      .subscribe({
        next: (achados) => this.achados.set(achados),
        error: () => undefined,
      });
  }

  abrir(): void {
    this.aberto.set(true);
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
    this.acoesDisponiveis.set([]);
    this.erro.set(null);
  }

  rodar(acaoId: string): void {
    const modulo = this.moduloAtual();
    if (!modulo || this.acaoRodando()) {
      return;
    }

    this.acaoRodando.set(acaoId);
    this.erro.set(null);

    this.http
      .get<AchadoAuditoria[]>(`${MCP_API_BASE_URL}/api/auditoria`, { params: { modulo, acao: acaoId } })
      .subscribe({
        next: (achados) => {
          this.achados.set(achados);
          this.acaoRodando.set(null);
          this.mudancas.update((atual) => atual + 1);
        },
        error: () => {
          this.erro.set('Não foi possível rodar essa verificação. Verifique se o servidor está em execução.');
          this.acaoRodando.set(null);
        },
      });
  }

  selecionarModulo(modulo: string): void {
    if (this.moduloAtual() === modulo) {
      return;
    }
    this.erro.set(null);
    this.moduloAtual.set(modulo);
    this.carregarAcoes(modulo);
    this.carregarConhecidos(modulo);
  }
}

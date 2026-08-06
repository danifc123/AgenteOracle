import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, effect, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../app-config';
import { ModuloHeader } from '../../../componentes/modulo-header/modulo-header';
import { Auditoria } from '../../../servicos/auditoria';
import { Sessao } from '../../../servicos/sessao';

export interface AchadoHistorico {
  execucao_id: string;
  usuario_id: string;
  modulo: string;
  view: string;
  campo: string;
  valor: string;
  descricao: string;
  criado_em: string;
  ativo: boolean;
}

@Component({
  selector: 'app-auditoria-historico',
  imports: [DatePipe, ModuloHeader],
  templateUrl: './auditoria-historico.html',
  styleUrl: './auditoria-historico.scss'
})
export class AuditoriaHistorico {
  private readonly http = inject(HttpClient);
  private readonly auditoria = inject(Auditoria);
  protected readonly sessao = inject(Sessao);

  protected readonly achados = signal<AchadoHistorico[]>([]);
  protected readonly carregando = signal(true);
  protected readonly erro = signal<string | null>(null);
  protected readonly alterandoAtivo = signal<string | null>(null);

  /** As ações de ativar/desativar são só pra teste/depuração — só quem tem
   * o papel `desenvolvedor` deveria nem ver a coluna. */
  protected readonly ehDesenvolvedor = () => this.sessao.papeis().includes('desenvolvedor');

  constructor() {
    // `mudancas()` incrementa toda vez que uma auditoria termina de rodar OU
    // um achado é dispensado (em qualquer tela, via sino) — o efeito roda
    // uma vez na criação (cobrindo a carga inicial da página) e de novo a
    // cada mudança nova, sem precisar que o usuário recarregue a tela.
    effect(() => {
      this.auditoria.mudancas();
      this.carregar();
    });
  }

  private carregar(): void {
    this.carregando.set(true);
    this.erro.set(null);

    this.http.get<AchadoHistorico[]>(`${MCP_API_BASE_URL}/api/auditoria/historico`).subscribe({
      next: (achados) => {
        this.achados.set(achados);
        this.carregando.set(false);
      },
      error: () => {
        this.erro.set('Não foi possível carregar a lista de auditoria. Verifique se o servidor está em execução.');
        this.carregando.set(false);
      }
    });
  }

  protected alternarAtivo(achado: AchadoHistorico): void {
    if (this.alterandoAtivo()) {
      return;
    }

    const chave = this.chaveAchado(achado);
    const novoAtivo = !achado.ativo;
    this.alterandoAtivo.set(chave);
    this.erro.set(null);

    this.http
      .patch(`${MCP_API_BASE_URL}/api/auditoria/historico/ativo`, {
        modulo: achado.modulo,
        view: achado.view,
        campo: achado.campo,
        valor: achado.valor,
        ativo: novoAtivo
      })
      .subscribe({
        next: () => {
          this.achados.update((atual) =>
            atual.map((item) => (this.chaveAchado(item) === chave ? { ...item, ativo: novoAtivo } : item))
          );
          this.alterandoAtivo.set(null);
        },
        error: () => {
          this.erro.set('Não foi possível alterar o status do achado.');
          this.alterandoAtivo.set(null);
        }
      });
  }

  protected chaveAchado(achado: AchadoHistorico): string {
    return `${achado.modulo}|${achado.view}|${achado.campo}|${achado.valor}`;
  }
}

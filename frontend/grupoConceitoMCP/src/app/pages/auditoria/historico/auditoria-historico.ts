import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../../app-config';
import { IconeOrdenacao } from '../../../componentes/icone-ordenacao/icone-ordenacao';
import { ModuloHeader } from '../../../componentes/modulo-header/modulo-header';
import { Auditoria } from '../../../servicos/auditoria';
import {
  compararValores,
  DirecaoOrdenacao,
  proximaDirecao,
} from '../../../servicos/ordenacao-tabela';
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
  imports: [DatePipe, IconeOrdenacao, ModuloHeader],
  templateUrl: './auditoria-historico.html',
  styleUrl: './auditoria-historico.scss',
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
        this.erro.set(
          'Não foi possível carregar a lista de auditoria. Verifique se o servidor está em execução.',
        );
        this.carregando.set(false);
      },
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
        ativo: novoAtivo,
      })
      .subscribe({
        next: () => {
          this.achados.update((atual) =>
            atual.map((item) =>
              this.chaveAchado(item) === chave ? { ...item, ativo: novoAtivo } : item,
            ),
          );
          this.alterandoAtivo.set(null);
        },
        error: () => {
          this.erro.set('Não foi possível alterar o status do achado.');
          this.alterandoAtivo.set(null);
        },
      });
  }

  protected chaveAchado(achado: AchadoHistorico): string {
    return `${achado.modulo}|${achado.view}|${achado.campo}|${achado.valor}`;
  }

  protected readonly colunaOrdenada = signal<string | null>(null);
  protected readonly direcaoOrdenacao = signal<DirecaoOrdenacao>(null);

  protected readonly achadosOrdenados = computed(() => {
    const coluna = this.colunaOrdenada();
    const direcao = this.direcaoOrdenacao();
    const lista = this.achados();
    if (!coluna || !direcao) {
      return lista;
    }

    const sinal = direcao === 'asc' ? 1 : -1;
    return [...lista].sort(
      (a, b) => compararValores(this.valorColuna(a, coluna), this.valorColuna(b, coluna)) * sinal,
    );
  });

  private valorColuna(achado: AchadoHistorico, coluna: string): unknown {
    switch (coluna) {
      case 'modulo':
        return achado.modulo;
      case 'campo':
        return achado.campo;
      case 'valor':
        return achado.valor;
      case 'descricao':
        return achado.descricao;
      case 'criado_em':
        return achado.criado_em;
      case 'status':
        return achado.ativo ? 1 : 0;
      default:
        return '';
    }
  }

  protected ordenarPor(coluna: string): void {
    if (this.colunaOrdenada() === coluna) {
      this.direcaoOrdenacao.set(proximaDirecao(this.direcaoOrdenacao()));
    } else {
      this.colunaOrdenada.set(coluna);
      this.direcaoOrdenacao.set('asc');
    }
  }

  protected direcaoDaColuna(coluna: string): DirecaoOrdenacao {
    return this.colunaOrdenada() === coluna ? this.direcaoOrdenacao() : null;
  }
}

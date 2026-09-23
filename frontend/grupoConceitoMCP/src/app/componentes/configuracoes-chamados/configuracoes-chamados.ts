import { HttpErrorResponse } from '@angular/common/http';
import { formatDate } from '@angular/common';
import {
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { finalize } from 'rxjs';
import {
  analisadosPorDez,
  percentualValido,
} from '../../servicos/amostragem-chamados/amostragem-chamados';
import {
  AlteracoesConfiguracoesTi,
  ConfiguracoesTi,
} from '../../servicos/configuracoes-ti/configuracoes-ti';
import { mensagemErro } from '../../servicos/mensagens-erro/mensagens-erro';
import { Toasts } from '../../servicos/toasts/toasts';
import { Botao } from '../botao/botao';
import { CampoNumerico } from '../campo-numerico/campo-numerico';
import { Dialog } from '../dialog/dialog';
import { Interruptor } from '../interruptor/interruptor';
import { SecaoConfiguracao } from '../secao-configuracao/secao-configuracao';

const MENSAGEM_PERCENTUAL_INVALIDO = 'Informe um número de 0 a 100, com até 3 casas decimais.';

function formatarPercentual(valor: number): string {
  return valor.toLocaleString('pt-BR', { maximumFractionDigits: 3 });
}

interface AvisoMudanca {
  tom: 'info' | 'atencao';
  texto: string;
}

/** Dialog de configurações da Auditoria (só desenvolvedor); edita um rascunho e só grava em "Salvar alterações". */
@Component({
  selector: 'app-configuracoes-chamados',
  imports: [Botao, CampoNumerico, Dialog, Interruptor, SecaoConfiguracao],
  templateUrl: './configuracoes-chamados.html',
  styleUrl: './configuracoes-chamados.scss',
})
export class ConfiguracoesChamados {
  private readonly configuracoes = inject(ConfiguracoesTi);
  private readonly toasts = inject(Toasts);

  aberto = input(false);
  fechar = output<void>();

  protected readonly usarIa = signal(true);
  protected readonly percentualTexto = signal('100');
  protected readonly lerAntigos = signal(false);
  protected readonly salvando = signal(false);
  protected readonly erroServidor = signal<string | null>(null);

  protected readonly percentual = computed(() => percentualValido(this.percentualTexto()));
  protected readonly erroPercentual = computed(() =>
    this.percentual() === null ? MENSAGEM_PERCENTUAL_INVALIDO : null,
  );
  protected readonly percentualTodos = computed(() => this.percentual() === 100);

  protected readonly alteracoes = computed<AlteracoesConfiguracoesTi>(() => {
    const alteracoes: AlteracoesConfiguracoesTi = {};
    if (this.usarIa() !== this.configuracoes.usarIaAvaliacaoChamado()) {
      alteracoes.usar_ia_avaliacao_chamado = this.usarIa();
    }
    const percentual = this.percentual();
    if (percentual !== null && percentual !== this.configuracoes.percentualAmostragemChamados()) {
      alteracoes.percentual_amostragem_chamados = percentual;
    }
    if (this.lerAntigos() !== this.configuracoes.lerChamadosAntigos()) {
      alteracoes.ler_chamados_antigos = this.lerAntigos();
    }
    return alteracoes;
  });

  protected readonly podeSalvar = computed(
    () =>
      Object.keys(this.alteracoes()).length > 0 &&
      this.erroPercentual() === null &&
      !this.salvando(),
  );

  protected readonly exemplo = computed(() => {
    const percentual = this.percentual();
    if (percentual === null) {
      return '';
    }
    if (percentual === 100) {
      return 'Todos os chamados novos são analisados.';
    }
    const analisados = analisadosPorDez(percentual);
    const verbo = analisados === 1 ? 'será analisado' : 'serão analisados';
    return (
      `De cada 10 chamados novos, ${analisados} ${verbo}. Sempre arredonda para baixo. ` +
      'Os que ficam de fora não são alterados no GLPI e não aparecem na tela.'
    );
  });

  protected readonly descricaoAntigos = computed(() => {
    if (this.percentualTodos()) {
      return 'Com 100%, todos os chamados são analisados e esta opção não tem efeito.';
    }
    const alteradoEm = this.configuracoes.percentualAlteradoEm();
    const referencia = alteradoEm
      ? `(${formatDate(alteradoEm, 'dd/MM/yyyy HH:mm', 'en-US')})`
      : '(ainda sem data: ela passa a existir na próxima vez que o percentual mudar)';
    return (
      `Chamado antigo é o criado antes da última mudança do percentual ${referencia}. ` +
      'Desligado: continua como está. Ligado: entra na conta do novo percentual.'
    );
  });

  protected readonly aviso = computed<AvisoMudanca | null>(() => {
    const percentual = this.percentual();
    if (percentual === null || !('percentual_amostragem_chamados' in this.alteracoes())) {
      return null;
    }
    const de = formatarPercentual(this.configuracoes.percentualAmostragemChamados());
    const para = formatarPercentual(percentual);
    const base = `Ao salvar, o percentual passa de ${de}% para ${para}%. Chamados criados antes desse momento serão considerados antigos.`;
    return percentual === 100
      ? {
          tom: 'info',
          texto: `${base} A partir daí, todos os chamados são analisados, inclusive os que tinham ficado de fora.`,
        }
      : {
          tom: 'atencao',
          texto: `${base} Os chamados que ficarem de fora não são alterados no GLPI.`,
        };
  });

  constructor() {
    effect(() => {
      if (this.aberto()) {
        untracked(() => this.iniciarRascunho());
      }
    });
  }

  private iniciarRascunho(): void {
    this.usarIa.set(this.configuracoes.usarIaAvaliacaoChamado());
    this.percentualTexto.set(String(this.configuracoes.percentualAmostragemChamados()));
    this.lerAntigos.set(this.configuracoes.lerChamadosAntigos());
    this.erroServidor.set(null);
    this.salvando.set(false);
  }

  protected cancelar(): void {
    if (!this.salvando()) {
      this.fechar.emit();
    }
  }

  protected salvar(): void {
    if (!this.podeSalvar()) {
      return;
    }

    this.salvando.set(true);
    this.erroServidor.set(null);
    this.configuracoes
      .salvar(this.alteracoes())
      .pipe(finalize(() => this.salvando.set(false)))
      .subscribe({
        next: () => {
          this.toasts.sucesso('Configurações salvas.');
          this.fechar.emit();
        },
        error: (erro: HttpErrorResponse) =>
          this.erroServidor.set(mensagemErro(erro, 'Não foi possível salvar as configurações.')),
      });
  }
}

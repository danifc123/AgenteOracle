import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';
import { LayoutRelatorio } from '../../dadosRelatorios/relatorio-layouts';
import { CoresCategoria } from '../../servicos/cores-categoria';
import { iniciais } from '../../servicos/iniciais';
import { mensagemErro } from '../../servicos/mensagens-erro';
import { Sessao } from '../../servicos/sessao';
import { Botao } from '../botao/botao';
import { ConfirmacaoDialog } from '../confirmacao-dialog/confirmacao-dialog';
import { Dialog } from '../dialog/dialog';

const TAMANHO_MAXIMO_ARQUIVO = 1_500_000; // ~1.5MB — a string base64 fica maior ainda, folga pro limite do backend

@Component({
  selector: 'app-configuracoes-usuario',
  imports: [Botao, ConfirmacaoDialog, Dialog],
  templateUrl: './configuracoes-usuario.html',
  styleUrl: './configuracoes-usuario.scss',
})
export class ConfiguracoesUsuario {
  private readonly http = inject(HttpClient);
  protected readonly sessao = inject(Sessao);
  protected readonly coresCategoria = inject(CoresCategoria);
  protected readonly iniciais = iniciais;

  protected readonly aberto = signal(false);
  protected readonly secaoAtiva = signal<'perfil' | 'senha' | 'layouts' | 'cores'>('perfil');
  protected readonly ABAS = [
    { id: 'perfil', rotulo: 'Perfil' },
    { id: 'senha', rotulo: 'Senha' },
    { id: 'layouts', rotulo: 'Layouts salvos' },
    { id: 'cores', rotulo: 'Cores das categorias' },
  ] as const;

  protected readonly nome = signal('');
  protected readonly fotoPreview = signal<string | null>(null);
  protected readonly fotoExpandida = signal(false);
  protected readonly salvandoPerfil = signal(false);
  protected readonly erroPerfil = signal<string | null>(null);

  protected readonly senhaAtual = signal('');
  protected readonly senhaNova = signal('');
  protected readonly senhaConfirmacao = signal('');
  protected readonly salvandoSenha = signal(false);
  protected readonly erroSenha = signal<string | null>(null);
  protected readonly senhaAlterada = signal(false);

  protected readonly layouts = signal<LayoutRelatorio[]>([]);
  protected readonly carregandoLayouts = signal(false);
  protected readonly editandoLayoutId = signal<number | null>(null);
  protected readonly nomeEdicaoLayout = signal('');
  protected readonly salvandoLayoutId = signal<number | null>(null);
  protected readonly layoutParaApagar = signal<LayoutRelatorio | null>(null);
  protected readonly apagandoLayoutId = signal<number | null>(null);
  protected readonly erroLayouts = signal<string | null>(null);

  protected readonly mensagemConfirmacaoApagarLayout = computed(() => {
    const layout = this.layoutParaApagar();
    return layout ? `Apagar o layout "${layout.nome}"? Essa ação não pode ser desfeita.` : '';
  });

  protected readonly salvandoCorCategoria = signal<string | null>(null);
  protected readonly erroCores = signal<string | null>(null);

  abrir(): void {
    this.secaoAtiva.set('perfil');
    this.nome.set(this.sessao.nome());
    this.fotoPreview.set(this.sessao.foto());
    this.fotoExpandida.set(false);
    this.erroPerfil.set(null);
    this.senhaAtual.set('');
    this.senhaNova.set('');
    this.senhaConfirmacao.set('');
    this.erroSenha.set(null);
    this.senhaAlterada.set(false);
    this.aberto.set(true);
    this.carregarLayouts();
  }

  private carregarLayouts(): void {
    this.carregandoLayouts.set(true);
    this.erroLayouts.set(null);

    this.http
      .get<LayoutRelatorio[]>(`${MCP_API_BASE_URL}/api/financeiro/relatorio/layouts`)
      .subscribe({
        next: (layouts) => {
          this.layouts.set(layouts);
          this.carregandoLayouts.set(false);
        },
        error: () => {
          this.layouts.set([]);
          this.carregandoLayouts.set(false);
        },
      });
  }

  protected alterarCor(categoria: string, cor: string): void {
    this.salvandoCorCategoria.set(categoria);
    this.erroCores.set(null);

    this.coresCategoria.definirCor(categoria, cor).subscribe({
      next: () => {
        this.coresCategoria.aplicarCorLocal(categoria, cor);
        this.salvandoCorCategoria.set(null);
      },
      error: (erro: HttpErrorResponse) => {
        this.erroCores.set(mensagemErro(erro, 'Não foi possível salvar a cor.'));
        this.salvandoCorCategoria.set(null);
      },
    });
  }

  alterarSenha(): void {
    if (!this.senhaAtual() || !this.senhaNova()) {
      this.erroSenha.set('Preencha a senha atual e a nova senha.');
      return;
    }

    if (this.senhaNova() !== this.senhaConfirmacao()) {
      this.erroSenha.set('A confirmação não bate com a nova senha.');
      return;
    }

    this.salvandoSenha.set(true);
    this.erroSenha.set(null);
    this.senhaAlterada.set(false);

    this.http
      .patch(`${MCP_API_BASE_URL}/api/auth/senha`, {
        senha_atual: this.senhaAtual(),
        senha_nova: this.senhaNova(),
      })
      .subscribe({
        next: () => {
          this.senhaAtual.set('');
          this.senhaNova.set('');
          this.senhaConfirmacao.set('');
          this.senhaAlterada.set(true);
          this.salvandoSenha.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erroSenha.set(mensagemErro(erro, 'Não foi possível trocar a senha.'));
          this.salvandoSenha.set(false);
        },
      });
  }

  protected apagarLayout(layout: LayoutRelatorio): void {
    if (this.apagandoLayoutId()) {
      return;
    }
    this.layoutParaApagar.set(layout);
  }

  protected cancelarApagarLayout(): void {
    if (this.apagandoLayoutId()) {
      return;
    }
    this.layoutParaApagar.set(null);
  }

  protected cancelarEdicaoLayout(): void {
    this.editandoLayoutId.set(null);
  }

  protected clicarAvatar(inputFoto: HTMLInputElement): void {
    if (this.fotoPreview()) {
      this.fotoExpandida.set(true);
    } else {
      inputFoto.click();
    }
  }

  protected confirmarApagarLayout(): void {
    const layout = this.layoutParaApagar();
    if (!layout || this.apagandoLayoutId()) {
      return;
    }

    this.apagandoLayoutId.set(layout.id);
    this.erroLayouts.set(null);

    this.http
      .delete(`${MCP_API_BASE_URL}/api/financeiro/relatorio/layouts/${layout.id}`)
      .subscribe({
        next: () => {
          this.layouts.update((atual) => atual.filter((item) => item.id !== layout.id));
          this.apagandoLayoutId.set(null);
          this.layoutParaApagar.set(null);
        },
        error: (erro: HttpErrorResponse) => {
          this.erroLayouts.set(mensagemErro(erro, 'Não foi possível apagar o layout.'));
          this.apagandoLayoutId.set(null);
        },
      });
  }

  fechar(): void {
    // Com a foto ampliada ou uma confirmação de exclusão aberta, o primeiro
    // Esc/clique-fora só fecha essa camada — fechar o dialog inteiro junto
    // seria surpreendente pro usuário. (Cada `app-dialog` trata Esc por
    // conta própria via `HostListener`, então os dois `fechar()` disparam
    // juntos numa mesma tecla — por isso esse método também precisa saber
    // ceder a vez pra camada de cima.)
    if (this.fotoExpandida()) {
      this.fotoExpandida.set(false);
      return;
    }
    if (this.layoutParaApagar()) {
      this.cancelarApagarLayout();
      return;
    }
    if (this.salvandoPerfil() || this.salvandoSenha()) {
      return;
    }
    this.aberto.set(false);
  }

  protected fecharFotoExpandida(): void {
    this.fotoExpandida.set(false);
  }

  protected iniciarEdicaoLayout(layout: LayoutRelatorio): void {
    this.editandoLayoutId.set(layout.id);
    this.nomeEdicaoLayout.set(layout.nome);
    this.erroLayouts.set(null);
  }

  protected redefinirCor(categoria: string): void {
    this.salvandoCorCategoria.set(categoria);
    this.erroCores.set(null);

    this.coresCategoria.redefinirCor(categoria).subscribe({
      next: () => {
        this.coresCategoria.removerCorLocal(categoria);
        this.salvandoCorCategoria.set(null);
      },
      error: (erro: HttpErrorResponse) => {
        this.erroCores.set(mensagemErro(erro, 'Não foi possível redefinir a cor.'));
        this.salvandoCorCategoria.set(null);
      },
    });
  }

  removerFoto(evento: Event): void {
    evento.preventDefault();
    evento.stopPropagation();
    // String vazia (não null) sinaliza "apagar a foto que já existe" pro
    // backend — null significa "não mexer no que já está salvo".
    this.fotoPreview.set('');
    this.erroPerfil.set(null);
  }

  protected salvarEdicaoLayout(layout: LayoutRelatorio): void {
    const nome = this.nomeEdicaoLayout().trim();
    if (!nome) {
      this.erroLayouts.set('Nome não pode ficar em branco.');
      return;
    }

    this.salvandoLayoutId.set(layout.id);
    this.erroLayouts.set(null);

    this.http
      .patch<LayoutRelatorio>(`${MCP_API_BASE_URL}/api/financeiro/relatorio/layouts/${layout.id}`, {
        nome,
      })
      .subscribe({
        next: (atualizado) => {
          this.layouts.update((atual) =>
            atual.map((item) => (item.id === atualizado.id ? atualizado : item)),
          );
          this.editandoLayoutId.set(null);
          this.salvandoLayoutId.set(null);
        },
        error: (erro: HttpErrorResponse) => {
          this.erroLayouts.set(mensagemErro(erro, 'Não foi possível renomear o layout.'));
          this.salvandoLayoutId.set(null);
        },
      });
  }

  salvarPerfil(): void {
    if (!this.nome().trim()) {
      this.erroPerfil.set('Nome não pode ficar em branco.');
      return;
    }

    this.salvandoPerfil.set(true);
    this.erroPerfil.set(null);

    this.http
      .patch<{ nome: string; foto: string | null }>(`${MCP_API_BASE_URL}/api/auth/perfil`, {
        nome: this.nome().trim(),
        foto: this.fotoPreview(),
      })
      .subscribe({
        next: (resultado) => {
          this.sessao.atualizarPerfil({ nome: resultado.nome, foto: resultado.foto });
          this.salvandoPerfil.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erroPerfil.set(mensagemErro(erro, 'Não foi possível salvar o perfil.'));
          this.salvandoPerfil.set(false);
        },
      });
  }

  selecionarFoto(evento: Event): void {
    const arquivo = (evento.target as HTMLInputElement).files?.[0];
    if (!arquivo) {
      return;
    }

    if (!arquivo.type.startsWith('image/')) {
      this.erroPerfil.set('Escolha um arquivo de imagem.');
      return;
    }

    if (arquivo.size > TAMANHO_MAXIMO_ARQUIVO) {
      this.erroPerfil.set('Imagem muito grande — escolha uma menor que 1,5MB.');
      return;
    }

    this.erroPerfil.set(null);
    const leitor = new FileReader();
    leitor.onload = () => this.fotoPreview.set(leitor.result as string);
    leitor.readAsDataURL(arquivo);
  }

  protected totalColunasLayout(layout: LayoutRelatorio): number {
    return Object.values(layout.colunas_selecionadas).reduce(
      (total, colunas) => total + colunas.length,
      0,
    );
  }
}

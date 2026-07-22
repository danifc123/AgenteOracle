import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';
import { iniciais } from '../../servicos/iniciais';
import { Sessao } from '../../servicos/sessao';
import { Botao } from '../botao/botao';
import { Dialog } from '../dialog/dialog';

const TAMANHO_MAXIMO_ARQUIVO = 1_500_000; // ~1.5MB — a string base64 fica maior ainda, folga pro limite do backend

function mensagemErro(erro: HttpErrorResponse, mensagemPadrao: string): string {
  return erro.error?.erro || mensagemPadrao;
}

@Component({
  selector: 'app-configuracoes-usuario',
  imports: [Botao, Dialog],
  templateUrl: './configuracoes-usuario.html',
  styleUrl: './configuracoes-usuario.scss'
})
export class ConfiguracoesUsuario {
  private readonly http = inject(HttpClient);
  protected readonly sessao = inject(Sessao);
  protected readonly iniciais = iniciais;

  protected readonly aberto = signal(false);

  protected readonly nome = signal('');
  protected readonly fotoPreview = signal<string | null>(null);
  protected readonly salvandoPerfil = signal(false);
  protected readonly erroPerfil = signal<string | null>(null);

  protected readonly senhaAtual = signal('');
  protected readonly senhaNova = signal('');
  protected readonly senhaConfirmacao = signal('');
  protected readonly salvandoSenha = signal(false);
  protected readonly erroSenha = signal<string | null>(null);
  protected readonly senhaAlterada = signal(false);

  abrir(): void {
    this.nome.set(this.sessao.nome());
    this.fotoPreview.set(this.sessao.foto());
    this.erroPerfil.set(null);
    this.senhaAtual.set('');
    this.senhaNova.set('');
    this.senhaConfirmacao.set('');
    this.erroSenha.set(null);
    this.senhaAlterada.set(false);
    this.aberto.set(true);
  }

  fechar(): void {
    if (this.salvandoPerfil() || this.salvandoSenha()) {
      return;
    }
    this.aberto.set(false);
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

  removerFoto(evento: Event): void {
    evento.preventDefault();
    evento.stopPropagation();
    // String vazia (não null) sinaliza "apagar a foto que já existe" pro
    // backend — null significa "não mexer no que já está salvo".
    this.fotoPreview.set('');
    this.erroPerfil.set(null);
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
        foto: this.fotoPreview()
      })
      .subscribe({
        next: (resultado) => {
          this.sessao.atualizarPerfil({ nome: resultado.nome, foto: resultado.foto });
          this.salvandoPerfil.set(false);
        },
        error: (erro: HttpErrorResponse) => {
          this.erroPerfil.set(mensagemErro(erro, 'Não foi possível salvar o perfil.'));
          this.salvandoPerfil.set(false);
        }
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
        senha_nova: this.senhaNova()
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
        }
      });
  }
}

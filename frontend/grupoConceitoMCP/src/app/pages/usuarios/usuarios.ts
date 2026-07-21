import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { MCP_API_BASE_URL } from '../../app-config';
import { Botao } from '../../componentes/botao/botao';
import { Dialog } from '../../componentes/dialog/dialog';
import { OpcaoSelectBusca, SelectBusca } from '../../componentes/select-busca/select-busca';

interface Usuario {
  id: number;
  usuario: string;
  nome: string;
  papeis: string[];
  ativo: boolean;
}

interface Papel {
  slug: string;
  rotulo: string;
}

function mensagemErro(erro: HttpErrorResponse, mensagemPadrao: string): string {
  return erro.error?.erro || mensagemPadrao;
}

@Component({
  selector: 'app-usuarios',
  imports: [Botao, Dialog, SelectBusca],
  templateUrl: './usuarios.html',
  styleUrl: './usuarios.scss'
})
export class Usuarios {
  private readonly http = inject(HttpClient);

  usuarios = signal<Usuario[]>([]);
  papeisDisponiveis = signal<Papel[]>([]);
  carregando = signal(true);
  erro = signal<string | null>(null);

  dialogAberto = signal(false);
  criando = signal(false);
  erroForm = signal<string | null>(null);

  formUsuario = signal('');
  formNome = signal('');
  formSenha = signal('');
  formPapeis = signal<string[]>([]);

  constructor() {
    this.carregarUsuarios();
    this.carregarPapeis();
  }

  protected readonly opcoesPapeis = () =>
    this.papeisDisponiveis().map((papel): OpcaoSelectBusca => ({ valor: papel.slug, rotulo: papel.rotulo }));

  protected rotuloPapeis(slugs: string[]): string {
    const disponiveis = this.papeisDisponiveis();
    return slugs.map((slug) => disponiveis.find((papel) => papel.slug === slug)?.rotulo ?? slug).join(', ');
  }

  carregarUsuarios(): void {
    this.carregando.set(true);
    this.erro.set(null);

    this.http.get<Usuario[]>(`${MCP_API_BASE_URL}/api/auth/usuarios`).subscribe({
      next: (usuarios) => {
        this.usuarios.set(usuarios);
        this.carregando.set(false);
      },
      error: () => {
        this.erro.set('Não foi possível carregar os usuários.');
        this.carregando.set(false);
      }
    });
  }

  private carregarPapeis(): void {
    this.http.get<Papel[]>(`${MCP_API_BASE_URL}/api/auth/papeis`).subscribe({
      next: (papeis) => this.papeisDisponiveis.set(papeis),
      error: () => this.papeisDisponiveis.set([])
    });
  }

  abrirDialog(): void {
    this.formUsuario.set('');
    this.formNome.set('');
    this.formSenha.set('');
    this.formPapeis.set([]);
    this.erroForm.set(null);
    this.dialogAberto.set(true);
  }

  fecharDialog(): void {
    if (this.criando()) {
      return;
    }
    this.dialogAberto.set(false);
  }

  criarUsuario(): void {
    if (!this.formUsuario().trim() || !this.formNome().trim() || !this.formSenha().trim() || !this.formPapeis().length) {
      this.erroForm.set('Preencha usuário, nome, senha e ao menos um papel.');
      return;
    }

    this.criando.set(true);
    this.erroForm.set(null);

    this.http
      .post<Usuario>(`${MCP_API_BASE_URL}/api/auth/usuarios`, {
        usuario: this.formUsuario().trim(),
        nome: this.formNome().trim(),
        senha: this.formSenha(),
        papeis: this.formPapeis()
      })
      .subscribe({
        next: () => {
          this.criando.set(false);
          this.dialogAberto.set(false);
          this.carregarUsuarios();
        },
        error: (erro: HttpErrorResponse) => {
          this.erroForm.set(mensagemErro(erro, 'Não foi possível criar o usuário.'));
          this.criando.set(false);
        }
      });
  }
}

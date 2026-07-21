import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MCP_API_BASE_URL } from '../../app-config';
import { Botao } from '../../componentes/botao/botao';
import { DadosSessao, Sessao } from '../../servicos/sessao';

@Component({
  selector: 'app-login',
  imports: [Botao],
  templateUrl: './login.html',
  styleUrl: './login.scss'
})
export class Login {
  private readonly http = inject(HttpClient);
  private readonly sessao = inject(Sessao);
  private readonly router = inject(Router);

  usuario = signal('');
  senha = signal('');
  erro = signal<string | null>(null);
  entrando = signal(false);

  constructor() {
    if (this.sessao.autenticado()) {
      this.router.navigateByUrl('/');
    }
  }

  entrar(): void {
    if (!this.usuario().trim() || !this.senha().trim()) {
      this.erro.set('Informe usuário e senha.');
      return;
    }

    this.erro.set(null);
    this.entrando.set(true);

    this.http
      .post<DadosSessao>(`${MCP_API_BASE_URL}/api/auth/login`, {
        usuario: this.usuario().trim(),
        senha: this.senha()
      })
      .subscribe({
        next: (dados) => {
          this.sessao.entrar(dados);
          this.entrando.set(false);
          this.router.navigateByUrl('/');
        },
        error: () => {
          this.erro.set('Usuário ou senha inválidos.');
          this.entrando.set(false);
        }
      });
  }
}

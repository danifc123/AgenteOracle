import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MCP_API_BASE_URL } from '../../app-config';
import { Botao } from '../../componentes/botao/botao';
import { DadosSessao, Sessao } from '../../servicos/sessao';

@Component({
  selector: 'app-login',
  imports: [Botao],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login {
  private readonly http = inject(HttpClient);
  private readonly sessao = inject(Sessao);
  private readonly router = inject(Router);

  usuario = signal('');
  senha = signal('');
  erro = signal<string | null>(null);
  entrando = signal(false);
  segundosEspera = signal<number | null>(null);

  private intervaloEspera: ReturnType<typeof setInterval> | null = null;

  constructor() {
    if (this.sessao.autenticado()) {
      this.router.navigateByUrl('/');
    }
    inject(DestroyRef).onDestroy(() => this.pararContagem());
  }

  entrar(): void {
    if (this.segundosEspera() !== null) {
      return;
    }

    if (!this.usuario().trim() || !this.senha().trim()) {
      this.erro.set('Informe usuário e senha.');
      return;
    }

    this.erro.set(null);
    this.entrando.set(true);

    this.http
      .post<DadosSessao>(`${MCP_API_BASE_URL}/api/auth/login`, {
        usuario: this.usuario().trim(),
        senha: this.senha(),
      })
      .subscribe({
        next: (dados) => {
          this.sessao.entrar(dados);
          this.entrando.set(false);
          this.router.navigateByUrl('/');
        },
        error: (erro: HttpErrorResponse) => {
          this.entrando.set(false);
          const segundos = erro.status === 429 ? Number(erro.error?.segundos_espera) : NaN;

          if (Number.isFinite(segundos) && segundos > 0) {
            this.iniciarContagem(segundos);
          } else {
            this.erro.set(erro.error?.erro || 'Usuário ou senha inválidos.');
          }
        },
      });
  }

  private iniciarContagem(segundos: number): void {
    this.pararContagem();
    this.segundosEspera.set(Math.ceil(segundos));
    this.atualizarMensagemEspera();

    this.intervaloEspera = setInterval(() => {
      const restante = (this.segundosEspera() ?? 1) - 1;

      if (restante <= 0) {
        this.pararContagem();
        this.erro.set(null);
        return;
      }

      this.segundosEspera.set(restante);
      this.atualizarMensagemEspera();
    }, 1000);
  }

  private atualizarMensagemEspera(): void {
    this.erro.set(
      `Você errou a senha muitas vezes seguidas. Tente de novo em ${this.segundosEspera()}s.`,
    );
  }

  private pararContagem(): void {
    if (this.intervaloEspera !== null) {
      clearInterval(this.intervaloEspera);
      this.intervaloEspera = null;
    }
    this.segundosEspera.set(null);
  }
}

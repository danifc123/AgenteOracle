import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Botao } from '../../componentes/botao/botao';
import { Sessao } from '../../servicos/sessao';

@Component({
  selector: 'app-login',
  imports: [Botao],
  templateUrl: './login.html',
  styleUrl: './login.scss'
})
export class Login {
  private readonly sessao = inject(Sessao);
  private readonly router = inject(Router);

  usuario = signal('');
  senha = signal('');
  erro = signal<string | null>(null);

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
    this.sessao.entrar();
    this.router.navigateByUrl('/');
  }
}

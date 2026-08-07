import { Component, computed, effect, inject } from '@angular/core';
import { AchadoAuditoria, Auditoria } from '../../servicos/auditoria';
import { Sessao, rotuloModulo } from '../../servicos/sessao';
import { Botao } from '../botao/botao';
import { Dialog } from '../dialog/dialog';

/** Qual departamento auditar é escolhido AQUI dentro, não no sino — a lista
 * de opções vem de `sessao.modulos()` (já calculada no login a partir do
 * papel do usuário: só Financeiro, todos, etc — ver `tools/auth/papeis.py`),
 * então o seletor reflete permissão automaticamente, sem regra própria. Com
 * 1 opção só (o caso comum hoje), a escolha é automática e o seletor nem
 * aparece — só some visível pra quem realmente tem mais de um módulo. */
@Component({
  selector: 'app-auditoria-painel',
  imports: [Botao, Dialog],
  templateUrl: './auditoria-painel.html',
  styleUrl: './auditoria-painel.scss',
})
export class AuditoriaPainel {
  protected readonly auditoria = inject(Auditoria);
  private readonly sessao = inject(Sessao);

  protected readonly rotuloModulo = rotuloModulo;
  protected readonly modulosDisponiveis = this.sessao.modulos;

  protected readonly mostrarSeletor = computed(
    () => this.auditoria.moduloAtual() === null && this.modulosDisponiveis().length > 1,
  );

  protected readonly titulo = computed(() => {
    const modulo = this.auditoria.moduloAtual();
    return modulo ? `Auditoria de Dados — ${rotuloModulo(modulo)}` : 'Auditoria de Dados';
  });

  constructor() {
    // Só 1 módulo liberado: não faz sentido pedir pro usuário escolher algo
    // que não é escolha nenhuma — seleciona sozinho assim que o painel abre.
    effect(() => {
      if (!this.auditoria.aberto() || this.auditoria.moduloAtual() !== null) {
        return;
      }
      const modulos = this.modulosDisponiveis();
      if (modulos.length === 1) {
        this.auditoria.selecionarModulo(modulos[0]);
      }
    });
  }

  protected chaveAchado(achado: AchadoAuditoria): string {
    return `${achado.modulo}|${achado.view}|${achado.campo}|${achado.valor}`;
  }

  protected dispensar(achado: AchadoAuditoria): void {
    this.auditoria.dispensar(achado);
  }

  protected fechar(): void {
    this.auditoria.fechar();
  }

  protected rodar(): void {
    this.auditoria.buscar();
  }

  protected selecionarModulo(modulo: string): void {
    this.auditoria.selecionarModulo(modulo);
  }

  protected trocarModulo(): void {
    this.auditoria.limparSelecao();
  }
}

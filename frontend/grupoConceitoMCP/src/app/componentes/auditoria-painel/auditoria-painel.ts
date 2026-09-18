import { Component, computed, effect, inject, signal } from '@angular/core';
import { AchadoAuditoria, Auditoria } from '../../servicos/auditoria/auditoria';
import { Sessao, rotuloModulo } from '../../servicos/sessao/sessao';
import { Botao } from '../botao/botao';
import { Dialog } from '../dialog/dialog';

interface GrupoAchados {
  view: string;
  achados: AchadoAuditoria[];
}

/** Qual departamento auditar é escolhido AQUI dentro, não no sino — a lista
 * de opções vem de `sessao.modulos()` (já calculada no login a partir do
 * papel do usuário: só Financeiro, todos, etc — ver `tools/auth/papeis.py`),
 * então o seletor reflete permissão automaticamente, sem regra própria. Com
 * 1 opção só (o caso comum hoje), a escolha é automática e o seletor nem
 * aparece — só some visível pra quem realmente tem mais de um módulo.
 *
 * Dentro de um módulo, cada AÇÃO (`auditoria.acoesDisponiveis()`) roda
 * independente das outras — clicar em uma nunca dispara as demais (ver
 * `servicos/auditoria.ts`). Os achados (de qualquer ação, de execuções
 * passadas ou agora) aparecem agrupados por `view` (`gruposAchados`), pra
 * separar visualmente "isso veio de qual verificação" sem precisar guardar
 * a origem em cada achado. */
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

  // Um grupo por `view` distinta, na ordem em que cada uma apareceu pela
  // primeira vez na lista — não alfabética, pra não embaralhar a ordenação
  // que o backend já manda (mais recente/mais relevante primeiro).
  protected readonly gruposAchados = computed<GrupoAchados[]>(() => {
    const porView = new Map<string, AchadoAuditoria[]>();
    for (const achado of this.auditoria.achados()) {
      const lista = porView.get(achado.view) ?? [];
      lista.push(achado);
      porView.set(achado.view, lista);
    }
    return Array.from(porView, ([view, achados]) => ({ view, achados }));
  });

  // Recolhido por `view` (não por grupo em si — `gruposAchados` é recalculado
  // a cada mudança de `achados`, um objeto novo a cada vez, não dava pra
  // guardar o estado nele). Vazio por padrão: todo grupo começa expandido.
  protected readonly gruposRecolhidos = signal<Set<string>>(new Set());

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

  protected alternarGrupo(view: string): void {
    this.gruposRecolhidos.update((atual) => {
      const novo = new Set(atual);
      if (novo.has(view)) {
        novo.delete(view);
      } else {
        novo.add(view);
      }
      return novo;
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

  protected rodar(acaoId: string): void {
    this.auditoria.rodar(acaoId);
  }

  protected selecionarModulo(modulo: string): void {
    this.auditoria.selecionarModulo(modulo);
  }

  protected trocarModulo(): void {
    this.auditoria.limparSelecao();
  }
}

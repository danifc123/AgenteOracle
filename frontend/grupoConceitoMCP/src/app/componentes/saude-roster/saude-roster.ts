import { Component, computed, inject, input } from '@angular/core';
import { Selo } from '../selo/selo';
import { Sessao } from '../../servicos/sessao';

export interface TecnicoCarga {
  nome: string;
  /** Login do AgenteOracle (não do GLPI) — usado só pra destacar "esse
   * técnico é o usuário logado" no roster (mais confiável que comparar por
   * `nome`, que pode se repetir entre pessoas diferentes). */
  usuario: string;
  /** Chamados abertos atribuídos a este técnico (GLPI). */
  chamados_abertos: number;
}

export interface SaudeArea {
  area: 'infra' | 'sistemas' | 'processos';
  rotulo: string;
  quantidade: number;
  /** Roster da área. Opcional: se vier vazio/ausente, o cartão só mostra a contagem. */
  tecnicos?: TecnicoCarga[];
  /** Chamados aguardando atribuição nesta área. */
  chamados_fila?: number;
}

/** PAINEL DE DIAGNÓSTICO — "SAÚDE DO ROSTER DE TÉCNICOS (GLPI)"
 *
 * Substitui a lista de texto que existia inline em `chamados.html`. Mesma
 * origem de dados (`/api/ti/tecnicos/saude`, restrito a
 * `exigir_desenvolvedor`) e mesma regra de visibilidade: quem monta decide
 * com `sessao.ehDesenvolvedor()`, o componente só desenha.
 *
 * Só diagnóstico, por decisão de produto: nenhum botão de ação aqui — a
 * leitura é "área com zero técnico nunca recebe atribuição automática"
 * (causa real de um 500 em `escolher_tecnico`, `tools/ti/tecnicos.py`).
 *
 * `tecnicos` e `chamados_fila` são opcionais de propósito: enquanto o
 * backend não devolver esses campos o cartão degrada pra contagem pura,
 * sem quebrar. */
@Component({
  selector: 'app-saude-roster',
  imports: [Selo],
  templateUrl: './saude-roster.html',
  styleUrl: './saude-roster.scss',
})
export class SaudeRoster {
  private readonly sessao = inject(Sessao);

  areas = input.required<SaudeArea[]>();

  protected readonly total = computed(() => this.areas().length);
  protected readonly cobertas = computed(() => this.areas().filter((a) => a.quantidade > 0).length);
  protected readonly vazias = computed(() => this.total() - this.cobertas());
  protected readonly percentualCobertura = computed(() =>
    this.total() === 0 ? 0 : Math.round((this.cobertas() / this.total()) * 100),
  );

  /** Chamados presos em área sem técnico — o número que realmente dói. */
  protected readonly filaSemDestino = computed(() =>
    this.areas().reduce((soma, a) => (a.quantidade === 0 ? soma + (a.chamados_fila ?? 0) : soma), 0),
  );

  /** Escala comum das barrinhas de carga, pra comparar técnico com técnico. */
  private readonly maiorCarga = computed(() =>
    Math.max(1, ...this.areas().flatMap((a) => (a.tecnicos ?? []).map((t) => t.chamados_abertos))),
  );

  protected larguraCarga(tecnico: TecnicoCarga): string {
    return `${Math.round((tecnico.chamados_abertos / this.maiorCarga()) * 100)}%`;
  }

  protected iniciais(nome: string): string {
    return nome
      .trim()
      .split(/\s+/)
      .slice(0, 2)
      .map((parte) => parte[0] ?? '')
      .join('')
      .toUpperCase();
  }

  protected plural(quantidade: number, singular: string, plural: string): string {
    return quantidade === 1 ? singular : plural;
  }

  /** Destaca a própria linha do usuário logado no roster — comparação por
   * login (`tecnico.usuario`), não por `nome` (dois cadastros diferentes já
   * apareceram com o mesmo nome "Daniel Faria" no sistema). */
  protected ehVoce(tecnico: TecnicoCarga): boolean {
    return !!this.sessao.usuario() && tecnico.usuario === this.sessao.usuario();
  }
}

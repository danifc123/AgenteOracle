import { Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { map } from 'rxjs';
import { Busca } from '../../../componentes/busca/busca';
import { MenuOpcoes } from '../../../componentes/menu-opcoes/menu-opcoes';
import { MODULOS_FINANCEIRO, RotinaFinanceira } from '../../../dadosRelatorios/modulos-financeiro';

const LIMITE_FIXADOS = 3;

@Component({
  selector: 'app-modulo-financeiro',
  imports: [RouterLink, Busca, MenuOpcoes],
  templateUrl: './modulo.html',
  styleUrl: './modulo.scss'
})
export class ModuloFinanceiro {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  private readonly moduloId = toSignal(
    this.route.paramMap.pipe(map((params) => params.get('moduloId') ?? '')),
    { initialValue: this.route.snapshot.paramMap.get('moduloId') ?? '' }
  );

  protected readonly modulo = computed(() =>
    MODULOS_FINANCEIRO.find((item) => item.id === this.moduloId())
  );

  protected readonly termoBusca = signal('');
  private readonly fixados = signal<string[]>([]);

  private readonly rotinasOrdenadas = computed(() => {
    const rotinas = this.modulo()?.rotinas ?? [];
    const fixados = this.fixados();

    const fixadas = fixados
      .map((nome) => rotinas.find((rotina) => rotina.nome === nome))
      .filter((rotina): rotina is RotinaFinanceira => !!rotina);

    const restantes = rotinas.filter((rotina) => !fixados.includes(rotina.nome));

    return [...fixadas, ...restantes];
  });

  protected readonly rotinasFiltradas = computed(() => {
    const rotinas = this.rotinasOrdenadas();
    const termo = this.termoBusca().trim().toLowerCase();

    if (!termo) {
      return rotinas;
    }

    return rotinas.filter((rotina) => rotina.nome.toLowerCase().includes(termo));
  });

  constructor() {
    effect(() => {
      this.moduloId();
      this.termoBusca.set('');
      this.carregarFixados();
    });
  }

  protected estaFixado(rotina: RotinaFinanceira): boolean {
    return this.fixados().includes(rotina.nome);
  }

  protected limiteFixadosAtingido(): boolean {
    return this.fixados().length >= LIMITE_FIXADOS;
  }

  protected alternarFixado(rotina: RotinaFinanceira): void {
    const atual = this.fixados();

    if (atual.includes(rotina.nome)) {
      this.salvarFixados(atual.filter((nome) => nome !== rotina.nome));
      return;
    }

    if (atual.length >= LIMITE_FIXADOS) {
      return;
    }

    this.salvarFixados([rotina.nome, ...atual]);
  }

  protected visualizar(rotina: RotinaFinanceira): void {
    if (rotina.rota) {
      this.router.navigateByUrl(rotina.rota);
    }
  }

  private carregarFixados(): void {
    const salvos = localStorage.getItem(this.chaveFixados());
    this.fixados.set(salvos ? (JSON.parse(salvos) as string[]) : []);
  }

  private salvarFixados(nomes: string[]): void {
    this.fixados.set(nomes);
    localStorage.setItem(this.chaveFixados(), JSON.stringify(nomes));
  }

  private chaveFixados(): string {
    return `financeiro:${this.moduloId()}:fixados`;
  }
}

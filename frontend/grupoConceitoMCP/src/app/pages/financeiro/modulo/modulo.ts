import { Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { map } from 'rxjs';
import { Busca } from '../../../componentes/busca/busca';
import { MODULOS_FINANCEIRO } from '../../../dadosRelatorios/modulos-financeiro';
import { Botao } from "../../../componentes/botao/botao";

@Component({
  selector: 'app-modulo-financeiro',
  imports: [RouterLink, Busca, Botao],
  templateUrl: './modulo.html',
  styleUrl: './modulo.scss'
})
export class ModuloFinanceiro {
  private readonly route = inject(ActivatedRoute);

  private readonly moduloId = toSignal(
    this.route.paramMap.pipe(map((params) => params.get('moduloId') ?? '')),
    { initialValue: this.route.snapshot.paramMap.get('moduloId') ?? '' }
  );

  protected readonly modulo = computed(() =>
    MODULOS_FINANCEIRO.find((item) => item.id === this.moduloId())
  );

  protected readonly termoBusca = signal('');

  protected readonly rotinasFiltradas = computed(() => {
    const rotinas = this.modulo()?.rotinas ?? [];
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
    });
  }
}

import { Component, computed, inject, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { DetalheCandidato } from '../../../../componentes/detalhe-candidato/detalhe-candidato';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { AnaliseCurriculo, Candidato } from '../../../../servicos/analise-curriculo';

const LIMITE_RESUMO_TRUNCADO = 140;

/** MÓDULO RH — TELA "COLABORADORES" (2026-08)
 *
 * Pool de candidatos `contratado` — separado de "Análise de Candidato"
 * (que agora só mostra `ativo`) pra não misturar quem já foi efetivado
 * com quem ainda está em avaliação. Por enquanto só listagem/perfil, sem
 * ação própria — o que essa tela vai precisar fazer além disso ainda
 * está em definição; ponto de partida simples pra evoluir depois. */
@Component({
  selector: 'app-colaboradores',
  imports: [Botao, DetalheCandidato, Dialog, ModuloHeader],
  templateUrl: './colaboradores.html',
  styleUrl: './colaboradores.scss',
})
export class Colaboradores {
  protected readonly analiseCurriculo = inject(AnaliseCurriculo);

  protected readonly candidatoAberto = signal<Candidato | null>(null);

  protected readonly colaboradores = computed(() =>
    this.analiseCurriculo.candidatos().filter((candidato) => candidato.status === 'contratado'),
  );

  constructor() {
    this.analiseCurriculo.carregarCandidatos('contratado');
  }

  protected abrirDetalhe(candidato: Candidato): void {
    this.candidatoAberto.set(candidato);
  }

  protected baixarCurriculo(candidato: Candidato): void {
    this.analiseCurriculo.baixarCurriculo(candidato);
  }

  protected dataFormatada(criadoEm: string): string {
    return new Date(criadoEm).toLocaleDateString('pt-BR');
  }

  protected fecharDetalhe(): void {
    this.candidatoAberto.set(null);
  }

  protected resumoTruncado(candidato: Candidato): string {
    const resumo = candidato.resumo_perfil;
    return resumo.length > LIMITE_RESUMO_TRUNCADO ? `${resumo.slice(0, LIMITE_RESUMO_TRUNCADO)}...` : resumo;
  }
}

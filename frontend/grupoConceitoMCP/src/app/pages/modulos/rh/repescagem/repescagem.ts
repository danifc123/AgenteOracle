import { Component, computed, inject, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { DetalheCandidato } from '../../../../componentes/detalhe-candidato/detalhe-candidato';
import { Dialog } from '../../../../componentes/dialog/dialog';
import { EstadoVazio } from '../../../../componentes/estado-vazio/estado-vazio';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { AnaliseCurriculo, Candidato, ROTULOS_SENIORIDADE } from '../../../../servicos/analise-curriculo';
import { BuscaCandidatos, ResultadoBusca } from '../../../../servicos/busca-candidatos';

const LIMITE_RESUMO_TRUNCADO = 140;

type ModoRepescagem = 'lista' | 'busca';

/** MÓDULO RH — TELA "REPESCAGEM" (2026-08)
 *
 * Pool de candidatos `descartado` — quando surge uma vaga nova, vale
 * reconsiderar quem já foi dispensado antes de só olhar currículo novo.
 * Duas formas de revisitar, alternadas por aba (`modo`, mesmo padrão de
 * `ConfiguracoesUsuario.secaoAtiva`) dentro de uma seção só — evita a
 * tela virar dois blocos soltos (tabela + painel de busca) competindo
 * por atenção ao mesmo tempo: a lista simples (mesmo padrão de tabela de
 * "Análise de Candidato", só que `status = 'descartado'`) e a busca por
 * IA (mesmo mecanismo de "Selecionar Candidato" — ver
 * `BuscaCandidatos.buscar` — rodando sobre os descartados em vez dos
 * ativos). "Reativar" devolve o candidato pro pool `ativo`, tirando ele
 * daqui e passando a aparecer de novo em "Selecionar Candidato".
 * "Marcar como contratado" pula direto pra `Colaboradores` — útil quando
 * o RH decide contratar quem já tinha sido dispensado antes, sem precisar
 * reativar e descartar de novo em "Análise de Candidato" no meio do caminho.
 */
@Component({
  selector: 'app-repescagem',
  imports: [Botao, DetalheCandidato, Dialog, EstadoVazio, ModuloHeader],
  templateUrl: './repescagem.html',
  styleUrl: './repescagem.scss',
})
export class Repescagem {
  protected readonly analiseCurriculo = inject(AnaliseCurriculo);
  protected readonly busca = inject(BuscaCandidatos);

  protected readonly modo = signal<ModoRepescagem>('lista');
  protected readonly descricao = signal('');
  protected readonly buscaFeita = signal(false);
  protected readonly candidatoAberto = signal<Candidato | null>(null);
  protected readonly resultadoAberto = signal<ResultadoBusca | null>(null);

  protected readonly candidatosDescartados = computed(() =>
    this.analiseCurriculo.candidatos().filter((candidato) => candidato.status === 'descartado'),
  );

  constructor() {
    this.analiseCurriculo.carregarCandidatos('descartado');
  }

  protected abrirDetalhe(candidato: Candidato): void {
    this.candidatoAberto.set(candidato);
  }

  protected abrirPerfil(resultado: ResultadoBusca): void {
    this.resultadoAberto.set(resultado);
  }

  protected baixarCurriculo(candidato: { id: number; nome: string }): void {
    this.analiseCurriculo.baixarCurriculo(candidato);
  }

  protected baixarCurriculoResultado(resultado: ResultadoBusca): void {
    this.analiseCurriculo.baixarCurriculo({ id: resultado.candidato_id, nome: resultado.nome });
  }

  protected buscar(): void {
    const texto = this.descricao().trim();
    if (!texto) {
      return;
    }
    this.buscaFeita.set(true);
    this.busca.buscar(texto, 'descartado');
  }

  protected contratar(candidato: Candidato): void {
    this.analiseCurriculo.atualizarStatusCandidato(candidato.id, 'contratado');
    this.candidatoAberto.set(null);
  }

  protected contratarResultado(resultado: ResultadoBusca): void {
    this.analiseCurriculo.atualizarStatusCandidato(resultado.candidato_id, 'contratado');
    this.resultadoAberto.set(null);
  }

  protected dataFormatada(criadoEm: string): string {
    return new Date(criadoEm).toLocaleDateString('pt-BR');
  }

  protected fecharDetalhe(): void {
    this.candidatoAberto.set(null);
  }

  protected fecharPerfil(): void {
    this.resultadoAberto.set(null);
  }

  protected percentual(similaridade: number): string {
    return `${Math.round(similaridade * 100)}%`;
  }

  protected reativar(candidato: Candidato): void {
    this.analiseCurriculo.atualizarStatusCandidato(candidato.id, 'ativo');
    this.candidatoAberto.set(null);
  }

  protected resumoTruncado(candidato: Candidato): string {
    const resumo = candidato.resumo_perfil;
    return resumo.length > LIMITE_RESUMO_TRUNCADO ? `${resumo.slice(0, LIMITE_RESUMO_TRUNCADO)}...` : resumo;
  }

  protected rotuloSenioridade(resultado: ResultadoBusca): string {
    return ROTULOS_SENIORIDADE[resultado.nivel_senioridade];
  }
}

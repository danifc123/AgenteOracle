import { Component, inject, signal } from '@angular/core';
import { Botao } from '../../../../componentes/botao/botao';
import { ModuloHeader } from '../../../../componentes/modulo-header/modulo-header';
import { AnaliseCurriculo, ROTULOS_SENIORIDADE } from '../../../../servicos/analise-curriculo';
import { BuscaCandidatos, ResultadoBusca } from '../../../../servicos/busca-candidatos';

/** MÓDULO RH — TELA "SELECIONAR CANDIDATO" (2026-08)
 *
 * Substitui a tela antiga "Cadastrar Vagas" — não existe mais vaga
 * cadastrada formalmente. O RH descreve a necessidade em texto livre e a
 * busca (RAG, ver `agent/rh/busca_candidatos.py`) roda ao vivo contra o
 * pool de candidatos já analisados em "Análise de Candidato" — nada aqui
 * fica salvo, cada busca é independente da anterior.
 */
@Component({
  selector: 'app-selecionar-candidato',
  imports: [Botao, ModuloHeader],
  templateUrl: './selecionar-candidato.html',
  styleUrl: './selecionar-candidato.scss',
})
export class SelecionarCandidato {
  protected readonly busca = inject(BuscaCandidatos);
  private readonly analiseCurriculo = inject(AnaliseCurriculo);

  protected readonly descricao = signal('');

  protected baixarCurriculo(resultado: ResultadoBusca): void {
    this.analiseCurriculo.baixarCurriculo({ id: resultado.candidato_id, nome: resultado.nome });
  }

  protected buscar(): void {
    const texto = this.descricao().trim();
    if (!texto) {
      return;
    }
    this.busca.buscar(texto);
  }

  protected percentual(similaridade: number): string {
    return `${Math.round(similaridade * 100)}%`;
  }

  protected rotuloSenioridade(resultado: ResultadoBusca): string {
    return ROTULOS_SENIORIDADE[resultado.nivel_senioridade];
  }
}

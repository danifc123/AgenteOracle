import { Component, input } from '@angular/core';
import { PerfilEstruturado } from '../../servicos/analise-curriculo';
import { rotuloSenioridade, rotuloStatusFormacao } from '../../servicos/rotulos-candidato';

/** Corpo do dialog de detalhe de candidato — usado tanto em "Análise de
 * Candidato" (`Candidato`) quanto em "Selecionar Candidato"
 * (`ResultadoBusca`), que têm `perfil_estruturado: PerfilEstruturado`
 * idêntico apesar de serem tipos diferentes. O rodapé de ações (que difere
 * entre as duas telas) fica fora deste componente, direto no
 * `<app-dialog>` que envolve ele. */
@Component({
  selector: 'app-detalhe-candidato',
  imports: [],
  templateUrl: './detalhe-candidato.html',
  styleUrl: './detalhe-candidato.scss',
})
export class DetalheCandidato {
  resumo = input.required<string>();
  perfilEstruturado = input.required<PerfilEstruturado>();
  /** Só "Análise de Candidato" mostra a data de cadastro — já formatada
   * pelo chamador (`dataFormatada`), esse componente só decide se mostra. */
  dataCadastro = input<string | null>(null);

  protected readonly rotuloSenioridade = rotuloSenioridade;
  protected readonly rotuloStatusFormacao = rotuloStatusFormacao;
}

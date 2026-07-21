"""Script de criação manual de usuário (`agente-oracle-criar-usuario`) — não
existe tela de cadastro no sistema; time pequeno, novos usuários são raros e
cadastrados à mão por quem administra o Agente Oracle."""

import getpass

from agente_oracle.tools.auth.usuarios import criar_usuario


def main() -> None:
    print("Criar novo usuário do Agente Oracle\n")

    usuario = input("Usuário (login): ").strip()
    nome = input("Nome completo: ").strip()
    senha = getpass.getpass("Senha: ")
    confirmacao = getpass.getpass("Confirme a senha: ")

    if senha != confirmacao:
        print("\nAs senhas não coincidem. Nenhum usuário foi criado.")
        return

    papeis_texto = input("Papéis (separados por vírgula, ex: financeiro): ").strip()
    papeis = [papel.strip() for papel in papeis_texto.split(",") if papel.strip()]

    usuario_criado = criar_usuario(usuario, senha, nome, papeis)
    papeis_exibidos = ", ".join(usuario_criado["papeis"]) or "nenhum"
    print(f"\nUsuário '{usuario_criado['usuario']}' criado com sucesso (papéis: {papeis_exibidos}).")


if __name__ == "__main__":
    main()

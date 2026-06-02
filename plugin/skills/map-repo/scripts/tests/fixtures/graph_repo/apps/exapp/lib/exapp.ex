defmodule Exapp do
  alias Exapp.{Repo, Worker}
  import Exapp.Helpers
  use GenServer

  def start, do: Repo.init()
end
